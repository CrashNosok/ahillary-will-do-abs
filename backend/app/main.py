"""Точка входа FastAPI. Запуск: uvicorn app.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import health
from app.core.config import CORS_ORIGINS
from app.core.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    # На старте: каталоги data/ и таблицы БД (data/app.db).
    init_db()
    yield


app = FastAPI(title="ABS — личный трекер", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
