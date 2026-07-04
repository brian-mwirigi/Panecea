# POST /api/v1/agent/run — Receives a device_id, triggers the 7-step orchestration loop, and returns Contract B.

import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent.orchestrator import run_pipeline
from api.websocket import broadcast
from schemas.contract_b import ContractB
from services.vultr_inference import StreamToken

router = APIRouter()


class AgentRunRequest(BaseModel):
    raw_pdf_text: str
    vpc_id: str = "vpc-medical-01"


@router.post("/api/v1/agent/run", response_model=ContractB)
async def run_agent(request: AgentRunRequest):
    """
    Triggers the full 7-step PANACEA pipeline.
    Streams reasoning tokens to connected WebSocket clients in real time.
    Returns the final Contract B payload once the pipeline completes.
    """
    try:
        async def on_token(token: StreamToken) -> None:
            await broadcast({"type": token.type, "text": token.text})

        result = await run_pipeline(
            raw_pdf_text=request.raw_pdf_text,
            vpc_id=request.vpc_id,
            on_token=on_token,
        )
        return result

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
