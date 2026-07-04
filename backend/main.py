# FastAPI application entrypoint. Registers all routers and the WebSocket endpoint.

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes.agent import router as agent_router
from api.routes.health import router as health_router
from api.routes.manuals import router as manuals_router
from api.routes.policy import router as policy_router
from api.websocket import router as ws_router

app = FastAPI(
    title="PANACEA",
    description="Zero-Trust Immune System for Hospital Networks — Vultr-native AI agent backend.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        origin.strip()
        for origin in os.getenv("PANACEA_CORS_ORIGINS", "http://localhost:3000").split(",")
        if origin.strip()
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router)
app.include_router(agent_router)
app.include_router(manuals_router)
app.include_router(policy_router)
app.include_router(ws_router)
