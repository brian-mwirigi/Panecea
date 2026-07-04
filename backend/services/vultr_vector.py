"""Vultr Vector Store ingestion for medical-device manuals.

This module deliberately talks to Vultr's managed Vector Store API directly.
It has no local database or alternate vector-store fallback.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from schemas.contract_a import ContractA


DEFAULT_BASE_URL = "https://api.vultrinference.com/v1/vector_store"


class VultrVectorStoreError(RuntimeError):
    """Raised when managed Vector Store ingestion cannot be completed."""


@dataclass(frozen=True)
class IngestionResult:
    collection_id: str
    source_doc_id: str
    item_ids: tuple[str, ...]
    chunk_count: int


def chunk_manual(text: str, chunk_size: int = 2_000, overlap: int = 200) -> list[str]:
    """Split manual text into bounded, overlapping chunks near natural boundaries."""
    if chunk_size <= 0:
        raise ValueError("chunk_size must be greater than zero")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must be non-negative and smaller than chunk_size")

    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise ValueError("manual text must not be empty")

    chunks: list[str] = []
    start = 0
    text_length = len(normalized)

    while start < text_length:
        end = min(start + chunk_size, text_length)
        if end < text_length:
            # Prefer a paragraph, line, sentence, or word boundary in the latter
            # half of the window. Fall back to an exact character boundary.
            lower_bound = start + chunk_size // 2
            candidates = (
                normalized.rfind("\n\n", lower_bound, end),
                normalized.rfind("\n", lower_bound, end),
                normalized.rfind(". ", lower_bound, end),
                normalized.rfind(" ", lower_bound, end),
            )
            boundary = max(candidates)
            # The chosen boundary must still advance beyond the requested
            # overlap; otherwise very large overlaps could stall the loop.
            if boundary > start + overlap:
                end = boundary + (2 if normalized[boundary:boundary + 2] in {"\n\n", ". "} else 1)

        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= text_length:
            break
        start = end - overlap

    return chunks


class VultrVectorStore:
    """Small async client for Vultr Serverless Inference Vector Store."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        collection_id: str | None = None,
        collection_name: str | None = None,
        timeout: float | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.api_key = api_key or os.getenv("VULTR_INFERENCE_API_KEY", "")
        self.base_url = (base_url or os.getenv("VULTR_VECTOR_STORE_URL") or DEFAULT_BASE_URL).rstrip("/")
        self.collection_id = collection_id or os.getenv("VULTR_VECTOR_COLLECTION_ID", "")
        self.collection_name = collection_name or os.getenv("VULTR_VECTOR_COLLECTION_NAME", "panacea-manuals")
        self.timeout = timeout or float(os.getenv("VULTR_VECTOR_TIMEOUT", "30"))
        self._client = client

        if not self.api_key:
            raise VultrVectorStoreError("VULTR_INFERENCE_API_KEY is required for Vultr Vector Store")
        if not self.collection_id and not self.collection_name:
            raise VultrVectorStoreError(
                "VULTR_VECTOR_COLLECTION_ID or VULTR_VECTOR_COLLECTION_NAME is required"
            )

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        last_error: Exception | None = None
        headers = self._headers.copy()
        if "files" in kwargs:
            headers.pop("Content-Type", None)
        for attempt in range(3):
            try:
                if self._client is not None:
                    response = await self._client.request(method, url, headers=headers, **kwargs)
                else:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.request(method, url, headers=headers, **kwargs)

                if response.status_code == 429 or response.status_code >= 500:
                    response.raise_for_status()
                if response.is_error:
                    detail = response.text[:500]
                    raise VultrVectorStoreError(
                        f"Vultr Vector Store returned HTTP {response.status_code}: {detail}"
                    )
                return response
            except (httpx.TimeoutException, httpx.NetworkError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < 2:
                    await asyncio.sleep(0.25 * (2**attempt))

        raise VultrVectorStoreError(f"Vultr Vector Store request failed after 3 attempts: {last_error}")

    async def ensure_collection(self) -> str:
        """Return the configured collection, creating it by name when necessary."""
        if self.collection_id:
            return self.collection_id

        response = await self._request("GET", self.base_url)
        for collection in _records(response.json(), "collections", "vector_stores"):
            if collection.get("name") == self.collection_name and collection.get("id"):
                self.collection_id = str(collection["id"])
                return self.collection_id

        response = await self._request(
            "POST",
            self.base_url,
            json={"name": self.collection_name},
        )
        self.collection_id = _response_id(response.json())
        return self.collection_id

    async def add_item(self, collection_id: str, content: str, description: str) -> str:
        response = await self._request(
            "POST",
            f"{self.base_url}/{collection_id}/items",
            json={"content": content, "description": description},
        )
        return _response_id(response.json())

    async def add_file(
        self,
        collection_id: str,
        filename: str,
        content: bytes,
        content_type: str = "application/pdf",
    ) -> str:
        """Upload the original document through Vultr Vector Store's file endpoint."""
        response = await self._request(
            "POST",
            f"{self.base_url}/{collection_id}/files",
            files={"file": (filename, content, content_type)},
        )
        return _response_id(response.json())

    async def ingest_manual(
        self,
        manual_text: str,
        contract: ContractA,
        *,
        chunk_size: int = 2_000,
        overlap: int = 200,
    ) -> IngestionResult:
        """Chunk a manual and store every chunk in Vultr with Contract A context."""
        chunks = chunk_manual(manual_text, chunk_size=chunk_size, overlap=overlap)
        collection_id = await self.ensure_collection()

        source_doc_id = contract.source_doc_id.strip()
        if not source_doc_id:
            digest = hashlib.sha256(manual_text.encode("utf-8")).hexdigest()[:16]
            source_doc_id = await self.add_item(
                collection_id,
                content=f"PANACEA manual source record sha256:{digest}",
                description=f"Source record for {contract.device_model} manual",
            )

        stored_contract = contract.model_copy(update={"source_doc_id": source_doc_id})
        contract_json = json.dumps(stored_contract.model_dump(), separators=(",", ":"))
        item_ids: list[str] = []

        for index, chunk in enumerate(chunks, start=1):
            content = (
                f"CONTRACT_A\n{contract_json}\n\n"
                f"MANUAL_CHUNK {index}/{len(chunks)}\n{chunk}"
            )
            description = (
                f"{stored_contract.device_model} {stored_contract.firmware_version}; "
                f"source {source_doc_id}; chunk {index}/{len(chunks)}"
            )
            item_ids.append(await self.add_item(collection_id, content, description))

        return IngestionResult(
            collection_id=collection_id,
            source_doc_id=source_doc_id,
            item_ids=tuple(item_ids),
            chunk_count=len(chunks),
        )

    async def rag_query(self, collection_id: str, query: str, model: str | None = None) -> str:
        """Ground a query in a Vultr Vector Store collection using Vultr RAG."""
        rag_url = self.base_url.rsplit("/vector_store", 1)[0] + "/chat/completions/RAG"
        response = await self._request(
            "POST",
            rag_url,
            json={
                "collection": collection_id,
                "model": model or os.getenv("VULTR_RAG_MODEL", "qwen2.5-32b-instruct"),
                "messages": [{"role": "user", "content": query}],
                "max_tokens": int(os.getenv("VULTR_RAG_MAX_TOKENS", "700")),
                "temperature": 0,
            },
        )
        try:
            message = response.json()["choices"][0]["message"]
            return message.get("content") or message.get("reasoning_content") or ""
        except (KeyError, IndexError, TypeError) as exc:
            raise VultrVectorStoreError("Unexpected response from Vultr RAG endpoint") from exc


async def ingest_manual(
    manual_text: str,
    contract: ContractA,
    *,
    chunk_size: int | None = None,
    overlap: int | None = None,
) -> IngestionResult:
    """Environment-configured ingestion entry point used by the orchestrator."""
    return await VultrVectorStore().ingest_manual(
        manual_text,
        contract,
        chunk_size=chunk_size if chunk_size is not None else int(os.getenv("VULTR_VECTOR_CHUNK_SIZE", "2000")),
        overlap=overlap if overlap is not None else int(os.getenv("VULTR_VECTOR_CHUNK_OVERLAP", "200")),
    )


async def query_manual(collection_id: str, contract: ContractA) -> str:
    """Retrieve manufacturer evidence relevant to a proposed policy."""
    ports = ", ".join(f"{item.protocol} {item.port}" for item in contract.allowed_ports) or "none"
    query = (
        f"For device {contract.device_model} firmware {contract.firmware_version}, return only the "
        f"manual evidence that justifies these network ports: {ports}. Include warnings or restrictions."
    )
    store = VultrVectorStore(collection_id=collection_id)
    last_error: Exception | None = None
    for attempt in range(4):
        if attempt:
            await asyncio.sleep(2 ** (attempt - 1))
        try:
            result = await store.rag_query(collection_id, query)
            if result.strip():
                return result
        except VultrVectorStoreError as exc:
            last_error = exc
    raise VultrVectorStoreError(f"Manual chunks were not queryable after indexing wait: {last_error}")


async def query_cve(device_model: str, firmware_version: str) -> str:
    """Query the Vultr-hosted CVE knowledge collection; never calls an external CVE API."""
    collection_id = os.getenv("VULTR_CVE_COLLECTION_ID", "")
    if not collection_id:
        raise VultrVectorStoreError("VULTR_CVE_COLLECTION_ID is required for CVE grounding")
    query = (
        f"Return known CVEs for medical device {device_model}, firmware {firmware_version}. "
        "Return concise JSON with cve_id, severity, affected_versions, and mitigation. "
        "Return cve_id NONE when the collection contains no matching evidence."
    )
    return await VultrVectorStore(collection_id=collection_id).rag_query(collection_id, query)


def _records(payload: Any, *keys: str) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("data", *keys):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
        if isinstance(value, dict):
            nested = _records(value, *keys)
            if nested:
                return nested
    return []


def _response_id(payload: Any) -> str:
    if isinstance(payload, dict):
        value = payload.get("id") or payload.get("file_id") or payload.get("item_id")
        if value is not None:
            return str(value)
        for key in ("data", "collection", "vector_store", "item", "file"):
            if key in payload:
                try:
                    return _response_id(payload[key])
                except VultrVectorStoreError:
                    pass
    raise VultrVectorStoreError("Vultr Vector Store response did not include a resource ID")
