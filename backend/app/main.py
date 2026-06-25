"""Точка входа FastAPI. Запуск: uvicorn app.main:app --reload"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import (
    achievements,
    activity,
    auth,
    body,
    body_photos,
    challenges,
    dashboard,
    exercises,
    food,
    goals,
    health,
    inbody,
    me_sports,
    progress,
    recommendations,
    snapshot,
    sponsors,
    sports,
    weight,
    workouts,
)
from app.core.config import CORS_ORIGINS
from app.core.db import init_db
from app.core.seed import (
    seed_initial_sport_levels,
    seed_initial_sports,
    seed_initial_user,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # На старте: каталоги data/ и таблицы БД (data/app.db), затем сид юзера, каталога спортов
    # и лестниц уровней дисциплин (уровни идут после спортов — им нужны их id).
    init_db()
    seed_initial_user()
    seed_initial_sports()
    seed_initial_sport_levels()
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
app.include_router(weight.router)
app.include_router(body_photos.router)
app.include_router(progress.router)
app.include_router(inbody.router)
app.include_router(sports.router)
app.include_router(sponsors.router)
app.include_router(challenges.router)
app.include_router(me_sports.router)
app.include_router(exercises.router)
app.include_router(workouts.router)
app.include_router(snapshot.router)
app.include_router(recommendations.router)
app.include_router(achievements.router)
