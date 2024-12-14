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
from tqdm import tqdm


# .env 파일 로드
env_path = Path(__file__).parent.parent / '.env'
logger.info(f"Loading environment variables from {env_path}")
load_dotenv(dotenv_path=env_path)

logging.langsmith("lunch-lens", "0.1.0")
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
BATCH_SIZE = 100_000  # 한 번에 처리할 레시피 수
SLEEP_TIME = 1  # 요청 간 대기 시간(초)

class FoodInfo(BaseModel):
    name: str
    category: str

def generate_recipe_ids(batch_num: int) -> List[str]:
    """100개의 레시피 ID 생성"""
    start = batch_num * BATCH_SIZE
    return [str(i).zfill(7) for i in range(start, start + BATCH_SIZE)]

def get_recipe_info(url: str) -> tuple[Optional[str], Optional[str]]:
    """레시피 페이지에서 레시피 이름과 이미지 URL 추출"""
    try:
        response = requests.get(url)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            recipe_title = soup.select_one('.view2_summary.st3 h3')
            recipe_image = soup.select_one('#main_thumbs')
            
            title = recipe_title.text.strip() if recipe_title else None
            image_url = recipe_image.get('src') if recipe_image else None
            
            # if not title:
            #     logger.info(f"Recipe title not found at {url}")
            # if not image_url:
            #     logger.info(f"Recipe image not found at {url}")
                
            return title, image_url
        else:
            logger.info(f"Failed to fetch recipe from {url}: Status code {response.status_code}")
    except Exception as e:
        logger.info(f"Error fetching recipe from {url}: {str(e)}")
    return None, None

def process_recipe_with_llm(name: str, llm) -> FoodInfo:
    """LLM을 사용하여 레시피 이름을 정제하고 카테고리 분류"""
    parser = PydanticOutputParser(pydantic_object=FoodInfo)
    
    template_path = Path(__file__).parent / 'templates' / 'categorize_food_template'
    with open(template_path, 'r', encoding='utf-8') as f:
        template_content = f.read()
    
    prompt = PromptTemplate(
        template=template_content,
        input_variables=["name"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )
    
    try:
        food_info = (prompt | llm | parser).invoke({"name": name})
        logger.info(f"LLM 프로세싱 결과: {food_info}")
        return food_info
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
    
    for recipe_id in tqdm(recipe_ids, desc="Processing recipes", total=len(recipe_ids)):
        url = f"https://www.10000recipe.com/recipe/{recipe_id}"
        
        recipe_name, image_url = get_recipe_info(url)
        if recipe_name:
            try:
                # logger.info(f"Found recipe: {recipe_name}")
                result = process_recipe_with_llm(recipe_name, llm)
                
                if result:
                    # 카테고리 확인/추가
                    category_query = """
                    INSERT INTO food_categories (name)
                    VALUES (%s)
                    ON CONFLICT (name) DO NOTHING
                    RETURNING id;
                    """
                    # logger.info(f"Executing category query with category: {result.category}")
                    category_result = postgres_hook.get_first(
                        category_query, 
                        parameters=(result.category,)
                    )
                    # logger.info(f"Category query result: {category_result}")
                    
                    if not category_result:
                        # 이미 존재하는 카테고리의 ID 가져오기
                        category_result = postgres_hook.get_first(
                            "SELECT id FROM food_categories WHERE name = %s",
                            parameters=(result.category,)
                        )
                        logger.info(f"Retrieved existing category ID: {category_result}")
                    
                    category_id = category_result[0] if category_result else None
                    
                    if category_id:
                        # 음식 메타데이터 추가
                        metadata_query = """
                        INSERT INTO food_metadata (name, category_id, image_url)
                        VALUES (%s, %s, %s)
                        ON CONFLICT (name) DO UPDATE SET
                            category_id = EXCLUDED.category_id,
                            image_url = EXCLUDED.image_url
                        RETURNING id;
                        """
                        # logger.info(f"Executing metadata query with values: name={result.name}, category_id={category_id}, image_url={image_url}")
                        try:
                            metadata_result = postgres_hook.get_first(
                                metadata_query,
                                parameters=(
                                    result.name,
                                    category_id,
                                    image_url
                                )
                            )
                            # logger.info(f"Metadata query result: {metadata_result}")
                            
                            if metadata_result:
                                # logger.info(f"Successfully processed recipe {recipe_id}: {result.name} ({result.category})")
                                success_count += 1
                            else:
                                logger.info(f"Failed to insert/update metadata for recipe {recipe_id}")
                                error_count += 1
                        except Exception as e:
                            logger.error(f"Database error while inserting metadata: {str(e)}")
                            error_count += 1
                    else:
                        logger.error(f"Failed to get category_id for category: {result.category}")
                        error_count += 1
                else:
                    logger.error(f"LLM 처리 결과가 None {recipe_id}: {result.name} ({result.category})")
                    error_count += 1
                
                time.sleep(SLEEP_TIME)
            except Exception as e:
                error_count += 1
        else:
            error_count += 1
        
    
    # 배치 처리 결과 요약
    success_rate = (success_count/len(recipe_ids))*100 if recipe_ids else 0
    
    logger.info(f"""
=== Batch Processing Summary ===
[BATCH {batch_num}] Processing completed
[STATS] Total recipes: {len(recipe_ids)}
[STATS] Success count: {success_count}
[STATS] Error count: {error_count}
[STATS] Success rate: {success_rate:.2f}%
==============================
    """.strip())
    
    # 현재 배치 번호를 DB에 저장
    postgres_hook.run("""
        INSERT INTO crawler_state (key, value)
        VALUES ('last_batch_number', %s)
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
    """, parameters=(batch_num,))

# DAG 정의
with DAG(
    dag_id='recipe_crawler',
    default_args=default_args,
    description='만개의 레시피 크롤링 DAG',
    schedule_interval='* * * * *',  # 매분 실행 (*/1과 동일)
    start_date=datetime(2024, 1, 1),
    catchup=False,
    max_active_runs=1,  # 동시에 하나의 DAG 인스턴스만 실행
    tags=['recipe', 'crawler'],
) as dag:
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
