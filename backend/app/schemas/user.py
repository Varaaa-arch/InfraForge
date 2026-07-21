from datetime import datetime 
from pydantic import BaseModel, EmailStr, ConfigDict, Field

class UserCreate(BaseModel): 
    username: str = Field(..., max_length=50)
    email: EmailStr 
    password: str = Field(..., min_length=8, max_length=255)

class UserRead(BaseModel): 
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    username: str
    email: EmailStr
    created_at: datetime
