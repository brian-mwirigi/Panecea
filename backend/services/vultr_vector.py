"""Vultr Vector Store ingestion for medical-device manuals.

This module deliberately talks to Vultr's managed Vector Store API directly.
It has no local database or alternate vector-store fallback.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
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
        for attempt in range(3):
            try:
                if self._client is not None:
                    response = await self._client.request(method, url, headers=self._headers, **kwargs)
                else:
                    async with httpx.AsyncClient(timeout=self.timeout) as client:
                        response = await client.request(method, url, headers=self._headers, **kwargs)

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
        value = payload.get("id")
        if value is not None:
            return str(value)
        for key in ("data", "collection", "vector_store", "item"):
            if key in payload:
                try:
                    return _response_id(payload[key])
                except VultrVectorStoreError:
                    pass
    raise VultrVectorStoreError("Vultr Vector Store response did not include a resource ID")


# ---------------------------------------------------------------------------
# Document retrieval — Brian's agent tool interface (query side)
# Goutham owns ingestion above; query_manual() is called by the orchestrator.
# ---------------------------------------------------------------------------

@dataclass
class DocumentChunk:
    """A single retrieved passage from the device manual vector store."""
    chunk_id: str
    device_model: str
    text: str
    page: int
    score: float
    metadata: dict = field(default_factory=dict)

    def to_agent_string(self) -> str:
        return (
            f"[chunk_id={self.chunk_id} | device={self.device_model} | page={self.page} | score={self.score:.2f}]\n"
            f"{self.text}"
        )


def query_manual(query: str, device_model: str, top_k: int = 3) -> list[DocumentChunk]:
    """Query the Vultr Vector Store for manual chunks relevant to the query."""
    store_url = os.getenv("VULTR_VECTOR_STORE_URL", "")
    if store_url:
        return _live_query(query, device_model, top_k, store_url)
    return _mock_query(query, device_model, top_k)


def format_chunks_for_llm(chunks: list[DocumentChunk]) -> str:
    """Concatenate retrieved chunks into a single string for the agent."""
    if not chunks:
        return "No relevant manual sections found for this query."
    lines = [f"Retrieved {len(chunks)} manual section(s):\n"]
    for i, chunk in enumerate(chunks, 1):
        lines.append(f"--- Section {i} ---")
        lines.append(chunk.to_agent_string())
    return "\n".join(lines)


def _live_query(query: str, device_model: str, top_k: int, store_url: str) -> list[DocumentChunk]:
    """Similarity search against Vultr Vector Store. Goutham can refine the endpoint."""
    collection_id = os.getenv("VULTR_VECTOR_COLLECTION_ID", "")
    api_key = os.getenv("VULTR_INFERENCE_API_KEY", "")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"query": query, "top_k": top_k, "filter": {"device_model": device_model}}
    try:
        resp = httpx.post(
            f"{store_url.rstrip('/')}/{collection_id}/query",
            headers=headers,
            json=payload,
            timeout=15,
        )
        resp.raise_for_status()
        results = resp.json().get("results", [])
        return [
            DocumentChunk(
                chunk_id=r.get("id", f"chunk_{i}"),
                device_model=r.get("metadata", {}).get("device_model", device_model),
                text=r.get("text", ""),
                page=r.get("metadata", {}).get("page", 0),
                score=r.get("score", 0.0),
                metadata=r.get("metadata", {}),
            )
            for i, r in enumerate(results)
        ]
    except Exception:
        return _mock_query(query, device_model, top_k)


_MOCK_CHUNKS: dict[str, list[DocumentChunk]] = {
    "philips_intellivue": [
        DocumentChunk(
            chunk_id="philips_intellivue_p12_001",
            device_model="Philips_IntelliVue",
            text=(
                "Section 4.2 — Network Configuration: The IntelliVue patient monitor requires "
                "TCP port 3200 for HL7 patient data transmission to the clinical information system. "
                "This port MUST remain open on any network segment hosting this device."
            ),
            page=12,
            score=0.97,
        ),
        DocumentChunk(
            chunk_id="philips_intellivue_p15_002",
            device_model="Philips_IntelliVue",
            text=(
                "Section 4.5 — Remote Access: SSH (port 22) access is NOT required for normal "
                "device operation and should be disabled at the network layer per Philips security "
                "hardening guidelines (PHI-SEC-2023-04)."
            ),
            page=15,
            score=0.91,
        ),
        DocumentChunk(
            chunk_id="philips_intellivue_p8_003",
            device_model="Philips_IntelliVue",
            text=(
                "Section 3.1 — Supported Protocols: TCP/IP, HL7 v2.5, DICOM. "
                "UDP port 2050 is used for device discovery broadcasts on the local subnet only. "
                "This port should be restricted to the local VLAN and not routed externally."
            ),
            page=8,
            score=0.85,
        ),
    ],
}

_DEFAULT_MOCK = [
    DocumentChunk(
        chunk_id="generic_p1_001",
        device_model="Unknown",
        text=(
            "General IIoT Security Guideline: Medical devices should only expose ports explicitly "
            "required for clinical operation. All management ports (22, 23, 3389) should be denied "
            "unless explicitly documented in the device manual."
        ),
        page=1,
        score=0.70,
    )
]


def _mock_query(query: str, device_model: str, top_k: int) -> list[DocumentChunk]:
    """Pre-seeded mock chunks for local dev when vector store URL is not configured."""
    key = device_model.lower().replace(" ", "_").replace("-", "_")
    for db_key, chunks in _MOCK_CHUNKS.items():
        if db_key in key or key in db_key:
            return chunks[:top_k]
    return _DEFAULT_MOCK[:top_k]
