# lunch-lens
personalized dish recommendation service

# MVP 기능
- 사용자의 이전 섭취 음식 리스트 입력
- 음식 리스트 기반 사용자 음식 섭취 취향 분석 후 다음 메뉴 추천

# 확장 기능
- 인증/인가
- 사용자 섭취 음식 리스트 저장
- 피드백 루프 반영
- 메뉴 업데이트

# ERD
```Mermaid
erDiagram

    %% Common audit fields (not explicitly listed):
    %% - created_at, created_by, updated_at, updated_by

    CRAWLING_HISTORY {
        string crawling_id PK
        string crawling_url
    }

    CATEGORY {
        string category_id PK
        string category_name
        string category_desc
    }

    MENU {
        string menu_id PK
        string menu_name
        string image_url
        string description
        string category_id FK
    }

    RECIPE {
        string recipe_id PK
        string menu_id FK
        string recipe_name
        string description
        string crawling_id FK
        string image_url
        string cook_time
        string difficulty
    }

    INGREDIENT {
        string ingredient_id PK
        string ingredient_name
        string image_url
        string description
    }

    UNIT {
        string unit_id PK
        string unit_name
        string unit_abbr
        string unit_type
        boolean is_base
        float conversion_to_base
        string base_unit_id FK
    }

    QUANTITY {
        string quantity_id PK
        string raw_input
        float normalized_value
        string unit_id FK
    }

    RECIPE_INGREDIENT {
        string recipe_ingredient_id PK
        string recipe_id FK
        string ingredient_id FK
        string quantity_id FK
    }

    MEMBER {
        string member_id PK
        string login_id
        string email
        string password
    }

    MEMBER_MENU_HISTORY {
        string history_id PK
        string member_id FK
        string menu_id FK
    }

    %% FEEDBACK_TYPE: category could be "implicit" or "explicit", value_type could be "binary", "rating", "text"
    FEEDBACK_TYPE {
        string feedback_type_id PK
        string feedback_type_name
        string category
        string value_type
        float weight
        boolean is_default
    }

    MEMBER_FEEDBACK {
        string feedback_id PK
        string member_id FK
        string recommendation_id FK
        datetime feedback_at
        string feedback_value
        string feedback_type_id FK
    }

    RECOMMENDATION {
        string recommendation_id PK
        string member_id FK
        string menu_id FK
        datetime recommended_at
        string preference_flag
    }

    %% Relationships
    MENU ||--o{ RECIPE : "1:N"
    MENU }o--|| CATEGORY : "N:1"
    RECIPE }o--|| CRAWLING_HISTORY : "N:1"
    RECIPE ||--o{ RECIPE_INGREDIENT : "1:N"
    RECIPE_INGREDIENT }o--|| INGREDIENT : "N:1"
    RECIPE_INGREDIENT }o--|| QUANTITY : "N:1"
    QUANTITY }o--|| UNIT : "N:1"
    MEMBER_MENU_HISTORY }o--|| MEMBER : "N:1"
    MEMBER_MENU_HISTORY }o--|| MENU : "N:1"
    RECOMMENDATION }o--|| MEMBER : "N:1"
    RECOMMENDATION }o--|| MENU : "N:1"
    MEMBER_FEEDBACK }o--|| MEMBER : "N:1"
    MEMBER_FEEDBACK }o--|| RECOMMENDATION : "N:1"
    MEMBER_FEEDBACK }o--|| FEEDBACK_TYPE : "N:1"
    UNIT }o--|| UNIT : "N:1"
```