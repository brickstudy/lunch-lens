import streamlit as st
import requests
import pandas as pd
from datetime import datetime

# FastAPI 서버 URL
API_URL = "http://fastapi:8000"

# Streamlit 앱 설정
st.set_page_config(page_title="Personalized Lunch Recommendation", layout="centered")
st.title("Personalized Lunch Recommendation Service")

# 섭취 기록 입력 섹션
st.header("Log Your Meal")
with st.form("log_form"):
    user_id = st.number_input("User ID", min_value=1, step=1)
    food_name = st.text_input("Food Name")
    rating = st.slider("Rating (1-5)", min_value=1, max_value=5, value=3)
    timestamp = datetime.now()
    submitted = st.form_submit_button("Log Meal")

    if submitted:
        # FastAPI에 섭취 기록 저장 요청
        data = {
            "user_id": user_id,
            "food_name": food_name,
            "timestamp": timestamp.isoformat(),
            "rating": rating,
        }
        response = requests.post(f"{API_URL}/log-food", json=data)
        if response.status_code == 200:
            st.success("Meal logged successfully!")
        else:
            st.error("Failed to log meal.")

# 추천 섹션
st.header("Get Your Lunch Recommendation")
user_id_for_recommendation = st.number_input("Enter Your User ID for Recommendation", min_value=1, step=1, key="recommend")
if st.button("Get Recommendation"):
    # FastAPI에 추천 요청
    response = requests.get(f"{API_URL}/recommend", params={"user_id": user_id_for_recommendation})
    if response.status_code == 200:
        recommended_food = response.json().get("recommended_food", "No recommendation available.")
        st.success(f"Today's Recommendation: {recommended_food}")
    else:
        st.error("Failed to fetch recommendation.")

# 섭취 이력 시각화 섹션
st.header("View Your Meal History")
if st.button("Load Meal History"):
    # FastAPI에서 섭초 이력 가져오기 (임시 데이터 사용)
    # 실제 구현에서는 API로 데이터 호출
    mock_data = [
        {"food_name": "Kimchi Stew", "timestamp": "2024-12-10", "rating": 4},
        {"food_name": "Pasta", "timestamp": "2024-12-11", "rating": 5},
        {"food_name": "Samgyeopsal", "timestamp": "2024-12-12", "rating": 3},
    ]
    df = pd.DataFrame(mock_data)
    st.table(df)
    st.bar_chart(df.set_index("food_name")["rating"])
