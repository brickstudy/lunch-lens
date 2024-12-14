-- 기본 테이블 생성
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 음식 카테고리 테이블
CREATE TABLE IF NOT EXISTS food_categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(50) NOT NULL UNIQUE
);

-- 음식 메타데이터 테이블
CREATE TABLE IF NOT EXISTS food_metadata (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL UNIQUE,
    category_id INTEGER REFERENCES food_categories(id),
    image_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 음식 섭취 로그 테이블
CREATE TABLE IF NOT EXISTS food_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    food_name VARCHAR(100) NOT NULL,
    rating INTEGER CHECK (rating >= 1 AND rating <= 5),
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- 기본 카테고리 데이터 삽입
INSERT INTO food_categories (name)
VALUES 
    ('한식'),
    ('양식'),
    ('중식'),
    ('일식'),
    ('기타')
ON CONFLICT (name) DO NOTHING;

-- 기본 음식 데이터 삽입 (카테고리 ID 참조)
INSERT INTO food_metadata (name, category_id, image_url) 
VALUES 
    ('김치찌개', (SELECT id FROM food_categories WHERE name = '한식'), 'https://example.com/kimchi-stew.jpg'),
    ('파스타', (SELECT id FROM food_categories WHERE name = '양식'), 'https://example.com/pasta.jpg'),
    ('삼겹살', (SELECT id FROM food_categories WHERE name = '한식'), 'https://example.com/samgyeopsal.jpg')
ON CONFLICT (name) DO NOTHING;

-- 필요한 권한 부여
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO admin;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO admin;
