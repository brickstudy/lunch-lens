from pydantic import BaseModel, Field

class FoodInfo(BaseModel):
    name: str = Field(description="The main dish name")
    category: str = Field(description="The category of the main dish")

class FoodInfoList(BaseModel):
    food_list: list[dict[str, str]] = Field(description="The list of main dish names and their categories")