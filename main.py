from fastapi import FastAPI, Depends, HTTPException, Request, status
from fastapi_jwt_auth import AuthJWT
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from pydantic import BaseModel
from models import Base, UserRole
from user_dal import UserDAL
from utils import hash_password, verify_password
from typing import Any
import os

load_dotenv()

class Settings(BaseModel):
    authjwt_secret_key: str

class UserCreate(BaseModel):
    email: str
    password: str
    role: UserRole = UserRole.viewer

class UserLogin(BaseModel):
    email: str
    password: str

DATABASE_URL = os.environ["DATABASE_URL"]

async def get_db(request: Request):
    async with request.app.state.SessionLocal() as session:
        yield session

@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = create_async_engine(
        DATABASE_URL,
        echo=True
    )
    SessionLocal = async_sessionmaker(
            bind=engine,
            expire_on_commit=False,
            class_=AsyncSession,
        )
    app.state.engine = engine
    app.state.SessionLocal = SessionLocal
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("Database Connection Ready")
    yield
    await engine.dispose()
    print("DB closed")

app = FastAPI(lifespan=lifespan)

@AuthJWT.load_config
def get_config() -> Any:
    return Settings(authjwt_secret_key=os.environ["JWT_SECRET_KEY"])

@app.post('/register', status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreate,
    db: AsyncSession = Depends(get_db),
    Authorize: AuthJWT = Depends()
):
    dal = UserDAL(db)
    existing_user = await dal.get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    hashed = hash_password(user_data.password)
    new_user = await dal.create_user(
        email=user_data.email,
        hashed_password=hashed,
        role=user_data.role
    )
    
    access_token = Authorize.create_access_token(subject=str(new_user.id))
    return {"access_token": access_token, "user_id": new_user.id}

@app.post("/login")
async def login(
    user_data: UserLogin,
    db: AsyncSession = Depends(get_db),
    Authorize: AuthJWT = Depends()
):
    dal = UserDAL(db)
    user = await dal.get_user_by_email(user_data.email)

    if not user or not verify_password(user_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password"
        )
        
    access_token = Authorize.create_access_token(subject=str(user.id))
    return {"access_token": access_token, "user_id": user.id}
