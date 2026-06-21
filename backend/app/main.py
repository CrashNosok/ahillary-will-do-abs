"""Точка входа FastAPI. Запуск: uvicorn app.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import activity, auth, body, dashboard, food, goals, health, progress
from app.core.config import CORS_ORIGINS
from app.core.db import init_db
from app.core.seed import seed_initial_user


@asynccontextmanager
async def lifespan(app: FastAPI):
    # На старте: каталоги data/ и таблицы БД (data/app.db), затем сид единственного юзера.
    init_db()
    seed_initial_user()
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
app.include_router(auth.router)
app.include_router(goals.router)
app.include_router(food.router)
app.include_router(activity.router)
app.include_router(dashboard.router)
app.include_router(body.router)
app.include_router(progress.router)
