"""Health-check эндпоинт: подтверждает, что бэкенд жив."""

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
