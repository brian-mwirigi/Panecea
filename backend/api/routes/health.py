# GET /healthz — Simple liveness check so Vultr and the frontend can confirm the backend is up.

from fastapi import APIRouter

router = APIRouter()


@router.get("/healthz")
async def health_check():
    return {"status": "ok", "service": "panacea-backend"}
