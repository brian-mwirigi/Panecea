# Vultr Serverless Inference API client. Sends prompts to the hosted LLM and returns streamed text responses via httpx.

import json
import sys
from pathlib import Path
from typing import AsyncGenerator

import httpx

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from config import (
    VULTR_FALLBACK_MODEL,
    VULTR_INFERENCE_API_KEY,
    VULTR_INFERENCE_BASE_URL,
    VULTR_INFERENCE_TIMEOUT,
    VULTR_MAIN_MODEL,
    VULTR_MAX_TOKENS,
    VULTR_TEMPERATURE,
)

HEADERS = {
    "Authorization": f"Bearer {VULTR_INFERENCE_API_KEY}",
    "Content-Type": "application/json",
}


def _build_payload(model: str, messages: list[dict]) -> dict:
    return {
        "model": model,
        "messages": messages,
        "stream": True,
        "max_tokens": VULTR_MAX_TOKENS,
        "temperature": VULTR_TEMPERATURE,
    }


def _extract_token(chunk: dict) -> str:
    delta = chunk["choices"][0]["delta"]
    return delta.get("content") or delta.get("reasoning") or delta.get("reasoning_content") or ""


async def _stream_model(model: str, messages: list[dict]) -> AsyncGenerator[str, None]:
    payload = _build_payload(model, messages)

    async with httpx.AsyncClient(timeout=VULTR_INFERENCE_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{VULTR_INFERENCE_BASE_URL}/chat/completions",
            headers=HEADERS,
            json=payload,
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line.startswith("data: "):
                    continue
                data = line[len("data: "):]
                if data.strip() == "[DONE]":
                    break
                try:
                    token = _extract_token(json.loads(data))
                    if token:
                        yield token
                except (json.JSONDecodeError, KeyError):
                    continue


async def stream_completion(messages: list[dict]) -> AsyncGenerator[str, None]:
    """
    Streams reasoning tokens from Nemotron via Vultr's OpenAI-compatible endpoint.
    Falls back to VULTR_FALLBACK_MODEL if the main model times out or errors.
    """
    try:
        async for token in _stream_model(VULTR_MAIN_MODEL, messages):
            yield token
    except httpx.TimeoutException:
        yield f"[WARN: {VULTR_MAIN_MODEL} timed out — retrying with {VULTR_FALLBACK_MODEL}]"
        try:
            async for token in _stream_model(VULTR_FALLBACK_MODEL, messages):
                yield token
        except httpx.TimeoutException:
            yield "[ERROR: Vultr Inference timeout — falling back to cached policy]"
        except httpx.HTTPStatusError as e:
            yield f"[ERROR: Vultr Inference returned {e.response.status_code}]"
        except Exception as e:
            yield f"[ERROR: {str(e)}]"
    except httpx.HTTPStatusError as e:
        yield f"[WARN: {VULTR_MAIN_MODEL} failed — retrying with {VULTR_FALLBACK_MODEL}]"
        try:
            async for token in _stream_model(VULTR_FALLBACK_MODEL, messages):
                yield token
        except Exception as fallback_error:
            yield f"[ERROR: Vultr Inference returned {e.response.status_code}; fallback failed: {fallback_error}]"
    except Exception as e:
        yield f"[ERROR: {str(e)}]"


async def complete(messages: list[dict]) -> str:
    """
    Non-streaming version. Collects the full response and returns it as a string.
    Used for steps that need a complete JSON output before proceeding.
    """
    full_response = []
    async for token in stream_completion(messages):
        full_response.append(token)
    return "".join(full_response)
