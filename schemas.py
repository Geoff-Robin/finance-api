from pydantic import BaseModel
from models import UserRole

class UserCreate(BaseModel):
    email: str
    password: str
    role: UserRole = UserRole.viewer

class UserLogin(BaseModel):
    email: str
    password: str
