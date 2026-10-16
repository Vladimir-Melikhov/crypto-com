from fastapi import APIRouter

router = APIRouter()


# Служебный эндпоинт для healthcheck контейнера, в документацию API не входит
@router.get("/health", include_in_schema=False)
async def health() -> dict[str, str]:
    return {"status": "ok"}
