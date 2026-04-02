from fastapi import FastAPI, Request
from fastapi_jwt_auth import AuthJWT
from dotenv import load_dotenv
from contextlib import asynccontextmanager
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from pydantic import BaseModel
from models import Base
from routers import auth, financial
from typing import Any
import os

load_dotenv()

class Settings(BaseModel):
    authjwt_secret_key: str

DATABASE_URL = os.environ["DATABASE_URL"]

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

# Include Routers
app.include_router(auth.router)
app.include_router(financial.router)

@app.get("/")
async def root():
    return {"message": "Zorvyn Financial Backend API"}
