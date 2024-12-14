from datetime import datetime, timedelta
import time
from typing import List, Optional, Dict
import os
from dotenv import load_dotenv
from pathlib import Path
import sys
import atexit
import signal

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow.providers.postgres.hooks.postgres import PostgresHook
import requests
from bs4 import BeautifulSoup
import itertools
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain.output_parsers import PydanticOutputParser
from langchain_teddynote import logging
from pydantic import BaseModel
from loguru import logger

# Airflow의 로그 파일에도 loguru 로그가 기록되도록 설정
logger.remove()  # 기존 핸들러 제거

# 시그널 핸들러 설정
def handle_signal(signum, frame):
    logger.info(f"Received signal {signum}. Cleaning up...")
    sys.exit(0)

signal.signal(signal.SIGTERM, handle_signal)
signal.signal(signal.SIGINT, handle_signal)

# stdout 핸들러
logger.add(
    sys.stdout,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
    enqueue=True  # 비동기 로깅 활성화
)

# 파일 핸들러
log_file = "/opt/airflow/logs/dag_processor_manager/task_logs.log"
logger.add(
    log_file,
    rotation="500 MB",
    retention="10 days",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level="INFO",
    enqueue=True,  # 비동기 로깅 활성화
    catch=True     # 예외 발생 시에도 계속 실행
)

# 종료 시 정리
@atexit.register
def cleanup():
    logger.info("Shutting down logger...")
    logger.complete()

# .env 파일 로드
env_path = Path(__file__).parent / '.env'
if env_path.exists():
    load_dotenv(env_path)

# 기본 설정
default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'start_date': datetime(2024, 12, 14),
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=5),
}

# 상수 정의
BASE_URL = "https://www.10000recipe.com/recipe/"
BATCH_SIZE = 1000  # 한 번에 처리할 레시피 수
SLEEP_TIME = 1  # 요청 간 대기 시간(초)

class FoodInfo(BaseModel):
    name: str
    category: str

def generate_recipe_ids(batch_num: int) -> List[str]:
    """100개의 레시피 ID 생성"""
    start = batch_num * 100
    return [str(i).zfill(7) for i in range(start, start + 100)]

def get_recipe_name(url: str) -> str:
    """레시피 페이지에서 레시피 이름 추출"""
    try:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            recipe_title = soup.select_one('.view2_summary.st3 h3')
            if recipe_title:
                return recipe_title.text.strip()
            logger.info(f"Recipe title not found at {url}")
        else:
            logger.info(f"Failed to fetch recipe from {url}: Status code {response.status_code}")
    except Exception as e:
        logger.info(f"Error fetching recipe from {url}: {str(e)}")
    return None

def process_recipe_with_llm(recipe_name: str, llm) -> FoodInfo:
    """LLM을 사용하여 레시피 이름을 정제하고 카테고리 분류"""
    parser = PydanticOutputParser(pydantic_object=FoodInfo)
    prompt = PromptTemplate(
        template="""Given the recipe title '{recipe_name}', please:
1. Remove any unnecessary descriptive words and return just the main dish name
2. Classify it into one of these categories: 한식, 양식, 중식, 일식, 기타

Format the response as:
{format_instructions}

Example:
Input: "백종원의 초간단 매콤 닭볶음탕"
Output:
{{"name": "닭볶음탕", "category": "한식"}}""",
        input_variables=["recipe_name"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    
    try:
        result = llm(prompt.format(recipe_name=recipe_name))
        return parser.parse(result)
    except Exception as e:
        logger.info(f"Error processing recipe with LLM: {str(e)}")
        return None

def get_next_batch_number(postgres_conn_id: str, **context) -> int:
    """다음 배치 번호 가져오기"""
    postgres_hook = PostgresHook(postgres_conn_id=postgres_conn_id)
    
    # 상태 테이블이 없으면 생성
    postgres_hook.run("""
        CREATE TABLE IF NOT EXISTS crawler_state (
            id SERIAL PRIMARY KEY,
            key VARCHAR(255) UNIQUE,
            value INTEGER
        )
    """)
    
    # 마지막 배치 번호 조회 또는 초기화
    result = postgres_hook.get_first("""
        INSERT INTO crawler_state (key, value)
        VALUES ('last_batch_number', '0')
        ON CONFLICT (key) DO NOTHING
        RETURNING value;
    """)
    
    if result is None:
        result = postgres_hook.get_first("""
            SELECT value 
            FROM crawler_state 
            WHERE key = 'last_batch_number'
        """)
    
    last_batch = int(result[0]) if result else 0
    next_batch = last_batch + 1
    
    # 다음 배치 번호 업데이트
    postgres_hook.run("""
        UPDATE crawler_state 
        SET value = %s 
        WHERE key = 'last_batch_number'
    """, parameters=[str(next_batch)])
    
    logger.info(f"Starting batch number: {next_batch}")
    return next_batch

def process_recipe_batch(postgres_conn_id: str, **context) -> None:
    """레시피 배치 처리"""
    batch_num = context['ti'].xcom_pull(task_ids='get_batch_number')
    recipe_ids = generate_recipe_ids(batch_num)
    
    logger.info(f"Processing batch {batch_num} with {len(recipe_ids)} recipes")
    success_count = 0
    error_count = 0
    
    postgres_hook = PostgresHook(postgres_conn_id=postgres_conn_id)
    llm = ChatOpenAI(temperature=0, model_name="gpt-4")
    
    for i, recipe_id in enumerate(recipe_ids, 1):
        url = f"https://www.10000recipe.com/recipe/{recipe_id}"
        logger.info(f"[{i}/{len(recipe_ids)}] Processing recipe ID {recipe_id}")
        
        recipe_name = get_recipe_name(url)
        if recipe_name:
            try:
                logger.info(f"Found recipe: {recipe_name}")
                result = process_recipe_with_llm(recipe_name, llm)
                
                if result:
                    # 카테고리 확인/추가
                    category_query = """
                    INSERT INTO food_categories (name)
                    VALUES (%s)
                    ON CONFLICT (name) DO NOTHING
                    RETURNING id;
                    """
                    category_id = postgres_hook.get_first(
                        category_query, 
                        parameters=(result.category,)
                    )[0]
                    
                    # 음식 메타데이터 추가
                    metadata_query = """
                    INSERT INTO food_metadata (name, category_id, image_url)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (name) DO NOTHING;
                    """
                    postgres_hook.run(
                        metadata_query,
                        parameters=(
                            result.name,
                            category_id,
                            url
                        )
                    )
                    
                    logger.info(f"Successfully processed recipe {recipe_id}: {result.name} ({result.category})")
                    success_count += 1
                else:
                    logger.info(f"LLM processing failed for recipe {recipe_id}")
                    error_count += 1
                
                time.sleep(SLEEP_TIME)
            except Exception as e:
                logger.info(f"Error processing recipe {recipe_id}: {str(e)}")
                error_count += 1
        else:
            logger.info(f"Recipe {recipe_id} not found or not accessible")
            error_count += 1
        
    
    # 배치 처리 결과 요약
    success_rate = (success_count/len(recipe_ids))*100 if recipe_ids else 0
    
    logger.info("=== Batch Processing Summary ===")
    logger.info(f"[BATCH {batch_num}] Processing completed")
    logger.info(f"[STATS] Total recipes: {len(recipe_ids)}")
    logger.info(f"[STATS] Success count: {success_count}")
    logger.info(f"[STATS] Error count: {error_count}")
    logger.info(f"[STATS] Success rate: {success_rate:.2f}%")
    logger.info("==============================")
    
    # 현재 배치 번호를 DB에 저장
    postgres_hook.run("""
        INSERT INTO crawler_state (key, value)
        VALUES ('last_batch_number', %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, parameters=(batch_num,))

# DAG 정의
dag = DAG(
    'recipe_crawler',
    default_args=default_args,
    description='만개의 레시피 크롤링 DAG',
    schedule_interval='*/5 * * * *',  # 5분마다 실행
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=['recipe', 'crawler'],
)

# 배치 번호 가져오기
get_batch_number = PythonOperator(
    task_id='get_batch_number',
    python_callable=get_next_batch_number,
    op_kwargs={
        'postgres_conn_id': 'lunch_lens_db'
    },
    provide_context=True,
    dag=dag,
)

# 레시피 처리
process_batch = PythonOperator(
    task_id='process_recipe_batch',
    python_callable=process_recipe_batch,
    op_kwargs={
        'postgres_conn_id': 'lunch_lens_db'
    },
    provide_context=True,
    dag=dag,
)

get_batch_number >> process_batch
