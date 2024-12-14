-- 기본 테이블 생성
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 음식 메타데이터 테이블
CREATE TABLE IF NOT EXISTS food_metadata (
    id SERIAL PRIMARY KEY,
    food_name VARCHAR(100) NOT NULL UNIQUE,
    category VARCHAR(50) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 음식 섭취 로그 테이블
CREATE TABLE IF NOT EXISTS food_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    food_name VARCHAR(100) NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (food_name) REFERENCES food_metadata(food_name)
);

-- 기본 음식 데이터 삽입
INSERT INTO food_metadata (food_name, category) 
VALUES 
    ('김치찌개', '한식'),
    ('파스타', '양식'),
    ('삼겹살', '한식')
ON CONFLICT (food_name) DO NOTHING;

-- 필요한 권한 부여
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO admin;
