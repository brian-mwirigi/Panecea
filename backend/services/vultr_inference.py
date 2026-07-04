# Vultr Serverless Inference API client. Sends prompts to the hosted LLM and returns streamed text responses via httpx.

import os
import json
from typing import AsyncGenerator

import httpx
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("VULTR_INFERENCE_API_KEY")
BASE_URL = os.getenv("VULTR_INFERENCE_BASE_URL", "https://api.vultrinference.com/v1")
MODEL = os.getenv("VULTR_INFERENCE_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")

HEADERS = {
    "Authorization": f"Bearer {API_KEY}",
    "Content-Type": "application/json",
}


async def stream_completion(messages: list[dict]) -> AsyncGenerator[str, None]:
    """
    Streams reasoning tokens from Nemotron via Vultr's OpenAI-compatible endpoint.
    Yields one text chunk at a time so the WebSocket can forward them live.
    """
    payload = {
        "model": MODEL,
        "messages": messages,
        "stream": True,
        "max_tokens": 1024,
        "temperature": 0.2,
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{BASE_URL}/chat/completions",
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
                        chunk = json.loads(data)
                        token = chunk["choices"][0]["delta"].get("content", "")
                        if token:
                            yield token
                    except (json.JSONDecodeError, KeyError):
                        continue

    except httpx.TimeoutException:
        yield "[ERROR: Vultr Inference timeout — falling back to cached policy]"
    except httpx.HTTPStatusError as e:
        yield f"[ERROR: Vultr Inference returned {e.response.status_code}]"
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
