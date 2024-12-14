from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
import datetime
import random
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import List
import os
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_teddynote.messages import stream_response
from langchain_teddynote import logging
from langchain.output_parsers import PydanticOutputParser

load_dotenv()

# 프로젝트 이름을 입력합니다.
logging.langsmith("lunch-lens", "0.1.0")

app = FastAPI()

# PostgreSQL 연결 설정
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:admin1234@postgres:5432/lunchlens")
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# llm 생성
llm = ChatOpenAI(temperature=0, model_name="gpt-4-turbo")

# 데이터베이스 모델
class FoodMetadata(Base):
    __tablename__ = "food_metadata"
    id = Column(Integer, primary_key=True, index=True)
    food_name = Column(String, unique=True, index=True)
    category = Column(String)
    created_at = Column(DateTime(timezone=True))

class FoodLog(Base):
    __tablename__ = "food_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    food_name = Column(String, ForeignKey("food_metadata.food_name"))
    rating = Column(Integer)
    timestamp = Column(DateTime(timezone=True), default=datetime.datetime.now)

# Pydantic 모델
class FoodLogCreate(BaseModel):
    user_id: int
    food_name: str
    rating: int
    timestamp: datetime.datetime

class FoodLogResponse(BaseModel):
    id: int
    user_id: int
    food_name: str
    rating: int
    timestamp: datetime.datetime

    class Config:
        orm_mode = True

# 의존성
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class FoodCategory(BaseModel):
    food_name: str
    category: str

def get_food_category(food_name: str) -> str:
    categories = ["한식", "중식", "양식", "일식", "기타"]
    try:
        parser = PydanticOutputParser(pydantic_object=FoodCategory)
        prompt_template = PromptTemplate(
            template="What is the category of {food_name}? The category should be one of {categories}. format={format_instructions}",
            input_variables=["food_name"],
            partial_variables={"categories": categories, "format_instructions": parser.get_format_instructions()},
        )
        chain = prompt_template | llm | parser
        answer: FoodCategory = chain.invoke({"food_name": food_name})
        return answer.category
    except Exception as e:
        raise e
        # return "Unknown"

@app.post("/log-food", response_model=FoodLogResponse)
def log_food(food: FoodLogCreate, db: Session = Depends(get_db)):
    # 음식이 메타데이터에 있는지 확인
    food_exists = db.query(FoodMetadata).filter(FoodMetadata.food_name == food.food_name).first()
    
    # 메타데이터에 없는 경우 자동으로 카테고리 생성 후 추가
    if not food_exists:
        category = get_food_category(food.food_name)
        new_food_metadata = FoodMetadata(
            food_name=food.food_name,
            category=category
        )
        db.add(new_food_metadata)
        db.commit()
        db.refresh(new_food_metadata)
    
    db_food_log = FoodLog(
        user_id=food.user_id,
        food_name=food.food_name,
        rating=food.rating,
        timestamp=food.timestamp
    )
    db.add(db_food_log)
    db.commit()
    db.refresh(db_food_log)
    return db_food_log

@app.get("/meal-history/{user_id}", response_model=List[FoodLogResponse])
def get_meal_history(user_id: int, db: Session = Depends(get_db)):
    logs = db.query(FoodLog).filter(
        FoodLog.user_id == user_id
    ).order_by(FoodLog.timestamp.desc()).all()
    return logs

@app.get("/recommend")
def recommend(user_id: int, db: Session = Depends(get_db)):
    # 사용자의 최근 음식 기록 가져오기
    recent_logs = db.query(FoodLog).filter(
        FoodLog.user_id == user_id
    ).order_by(FoodLog.timestamp.desc()).limit(5).all()
    
    # 최근에 먹지 않은 음식 중에서 추천
    recent_foods = {log.food_name for log in recent_logs}
    available_foods = db.query(FoodMetadata).filter(
        ~FoodMetadata.food_name.in_(recent_foods)
    ).all()
    
    if not available_foods:
        available_foods = db.query(FoodMetadata).all()
    
    recommended = random.choice(available_foods)
    return {"recommended_food": recommended.food_name}
