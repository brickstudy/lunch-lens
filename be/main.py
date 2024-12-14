from fastapi import FastAPI, Depends, HTTPException
from pydantic import BaseModel
import datetime
import random
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from typing import List
import os

app = FastAPI()

# PostgreSQL 연결 설정
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:admin1234@postgres:5432/lunchlens")
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

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

@app.post("/log-food", response_model=FoodLogResponse)
def log_food(food: FoodLogCreate, db: Session = Depends(get_db)):
    # 음식이 메타데이터에 있는지 확인
    food_exists = db.query(FoodMetadata).filter(FoodMetadata.food_name == food.food_name).first()
    if not food_exists:
        raise HTTPException(status_code=404, detail="Food not found in metadata")
    
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
