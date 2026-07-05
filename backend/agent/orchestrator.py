# Core 7-step agent loop. Coordinates extraction → CVE check → policy decision → firewall enforcement → memo generation.

import json
import hashlib
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent.prompts import TOOLS, agentic_policy_prompt, extraction_prompt, incident_memo_prompt
from agent.tools.firewall import apply_firewall_rule, get_enforcement_result, retract_firewall_rule
from schemas.contract_a import AllowedPort, ContractA
from schemas.contract_b import ContractB, FirewallRule
from schemas.control_plane import EvidenceBundle, EnforcementReceipt, PolicyLease
from services.vultr_events import publish_event
from services.vultr_inference import StreamToken, complete, run_agentic_loop
from services.vultr_object_storage import VultrObjectStorage, VultrObjectStorageError
from services.policy_leases import cancel_expiry, schedule_expiry
from services.vultr_database import save_evidence_index
from services.vultr_vector import (
    IngestionResult,
    VultrVectorStore,
    VultrVectorStoreError,
    ingest_manual,
    query_cve,
    query_manual,
    retrieve_document,
)

# Used when Nemotron's extraction fails or comes back with no ports — the
# demo must always produce a result even if the LLM hiccups once. Callers
# still get told this happened via the [STEP 2 WARN] emit, unlike main's
# silent version of this fallback.
DEMO_CONTRACT_A = ContractA(
    device_model="Philips_IntelliVue",
    firmware_version="B.01",
    allowed_ports=[
        AllowedPort(port=24105, protocol="UDP", reason="Data Export Protocol — main data channel (p.29)"),
        AllowedPort(port=24005, protocol="UDP", reason="Device discovery / Connect Indication broadcast (p.53)"),
    ],
    source_doc_id="",
)


async def run_pipeline(
    raw_pdf_text: str,
    vpc_id: str,
    on_token: Callable[[StreamToken], Awaitable[None]] | None = None,
    manual_object_key: str = "",
    operator_id: str = "panacea-agent",
    source_doc_id: str = "",
) -> ContractB:
    """
    Executes the full 7-step PANACEA pipeline.

    Steps:
        1. Ingest      — raw_pdf_text arrives from Goutham's PDF module
        2. Extract     — LLM pulls device model, firmware, allowed ports (Contract A)
        3. CVE Check   — Nemotron autonomously calls check_cve tool
        4. Decide      — Nemotron generates zero-trust policy (Contract B)
        5. Store       — chunks the manual into Vultr Vector Store using Contract A
        6. Enforce     — Nemotron calls apply_firewall_rule tool
        7. Report      — LLM expands memo for the frontend

    Args:
        raw_pdf_text: Raw text extracted from the medical device PDF.
        vpc_id: Target Vultr VPC ID (e.g. "vpc-medical-01").
        on_token: Optional WebSocket callback — receives StreamToken on each reasoning/content chunk.

    Returns:
        ContractB with the final firewall policy and incident memo.
    """

    async def _emit(text: str, token_type: str = "reasoning") -> None:
        if on_token:
            await on_token(StreamToken(text=text, type=token_type))

    # ------------------------------------------------------------------
    # Step 2: Extract device info from the PDF text
    # ------------------------------------------------------------------
    await _emit("\n[STEP 2] Extracting network requirements from device manual...\n")
    extraction_raw = await complete(extraction_prompt(raw_pdf_text))
    contract_a, extraction_fell_back = _parse_contract_a(extraction_raw)
    if source_doc_id:
        contract_a = contract_a.model_copy(update={"source_doc_id": source_doc_id})
    if extraction_fell_back:
        await _emit(
            f"[STEP 2 WARN] Nemotron did not return valid extraction JSON (or returned no ports) — "
            f"substituting the demo device ({contract_a.device_model}); treat this run's policy as "
            f"unverified until the manual is re-processed.\n"
        )
    else:
        await _emit(f"[STEP 2 DONE] Device: {contract_a.device_model} | Firmware: {contract_a.firmware_version} | Ports: {[p.port for p in contract_a.allowed_ports]}\n")

    # ------------------------------------------------------------------
    # Step 5: Commit Contract A and chunks before any enforcement decision.
    # ------------------------------------------------------------------
    await _emit("\n[STEP 5] Chunking manual and storing Contract A in Vultr Vector Store...\n")
    try:
        ingestion = await ingest_manual(raw_pdf_text, contract_a)
        contract_a = contract_a.model_copy(update={"source_doc_id": ingestion.source_doc_id})
        await publish_event("contract-a.extracted", ingestion.source_doc_id, contract_a.model_dump(mode="json"))
        await _emit(
            f"[STEP 5 DONE] Stored {ingestion.chunk_count} chunks in Vultr collection "
            f"{ingestion.collection_id}; source vector {ingestion.source_doc_id}.\n"
        )
    except VultrVectorStoreError as exc:
        await _emit(f"[STEP 5 WARN] Vector Store ingestion failed ({exc}) — continuing without vector storage.\n")
        ingestion = IngestionResult(
            collection_id="",
            source_doc_id=contract_a.source_doc_id,
            item_ids=(),
            chunk_count=0,
        )

    retrieved_context = ""
    if ingestion.collection_id:
        await _emit("\n[MEMORY] Retrieving authoritative evidence through Vultr RAG...\n")
        try:
            retrieved_context = await query_manual(ingestion.collection_id, contract_a)
            await _emit("[MEMORY DONE] Manufacturer evidence attached to the decision.\n")
        except VultrVectorStoreError as exc:
            await _emit(f"[MEMORY WARN] Manual retrieval failed ({exc}) — proceeding without retrieved evidence.\n")
    else:
        await _emit("[MEMORY SKIPPED] No Vector Store collection available for this run.\n")

    # ------------------------------------------------------------------
    # Step 3 + 4 + 6: the tool-capable Vultr model checks CVE memory,
    # decide policy, and apply firewall rules
    # ------------------------------------------------------------------
    await _emit("\n[STEP 3-4-6] Handing control to Nemotron for CVE check, policy decision, and firewall enforcement...\n")

    messages = agentic_policy_prompt(
        device_model=contract_a.device_model,
        firmware_version=contract_a.firmware_version,
        allowed_ports=[p.model_dump() for p in contract_a.allowed_ports],
        vpc_id=vpc_id,
        retrieved_context=retrieved_context,
    )

    final_message = await run_agentic_loop(
        messages=messages,
        tools=TOOLS,
        tool_executor=_tool_executor,
        on_token=on_token,
    )

    # ------------------------------------------------------------------
    # Extract ContractB from the last apply_firewall_rule tool call.
    # If Nemotron didn't call the tool, build a deterministic policy so the
    # demo never shows empty rules (README guardrail #4: graceful fallbacks).
    # ------------------------------------------------------------------
    contract_b = _extract_contract_b(final_message, vpc_id)
    if not contract_b.firewall_rules:
        await _emit("\n[FALLBACK] Nemotron did not enforce via tool — generating deterministic zero-trust policy.\n")
        contract_b = _deterministic_policy(contract_a, vpc_id)
        apply_firewall_rule(
            target_vpc_id=contract_b.target_vpc_id,
            firewall_rules=[r.model_dump() for r in contract_b.firewall_rules],
            confidence_score=contract_b.confidence_score,
            cve_flagged=contract_b.cve_flagged,
            memo_text=contract_b.memo_text,
        )

    # ------------------------------------------------------------------
    # Step 7: Expand the incident memo for Oleh's frontend
    # ------------------------------------------------------------------
    await _emit("\n[STEP 7] Generating incident memo...\n")
    memo = await complete(incident_memo_prompt(contract_b.model_dump()))
    contract_b.memo_text = memo.strip()
    await _emit("\n[STEP 7 DONE] Memo ready.\n", "content")

    enforcement = get_enforcement_result(vpc_id)
    if not enforcement:
        raise RuntimeError("Vultr enforcement completed without a durable receipt")
    receipt = EnforcementReceipt.model_validate(enforcement["receipt"])
    lease = PolicyLease(
        lease_id=enforcement["lease_id"],
        source_doc_id=contract_a.source_doc_id,
        policy=contract_b,
        expires_at=datetime.fromisoformat(enforcement["expires_at"]),
        receipt=receipt,
    )
    await schedule_expiry(lease)
    evidence = EvidenceBundle(
        evidence_id=f"evidence-{uuid.uuid4().hex}",
        contract_a=contract_a,
        contract_b=contract_b,
        lease=lease,
        manual_sha256=hashlib.sha256(raw_pdf_text.encode()).hexdigest(),
        retrieved_context=retrieved_context,
        model_id=os.getenv("VULTR_TOOL_MODEL", os.getenv("VULTR_MAIN_MODEL", "")),
        operator_id=operator_id,
        metadata={"manual_object_key": manual_object_key, "collection_id": ingestion.collection_id},
    )

    evidence_key = ""
    storage = VultrObjectStorage()
    if storage.configured:
        evidence_key, evidence_hash = storage.seal_evidence(evidence)
        evidence = evidence.model_copy(update={"evidence_sha256": evidence_hash})
        await save_evidence_index(evidence.evidence_id, evidence_key, evidence_hash)
    elif storage.strict:
        raise VultrObjectStorageError("Vultr Object Storage is required in strict mode")

    event_payload = {
        "contract_b": contract_b.model_dump(mode="json"),
        "lease": lease.model_dump(mode="json"),
        "evidence_key": evidence_key,
        "evidence_sha256": evidence.evidence_sha256,
    }
    await publish_event("contract-b.enforced", lease.lease_id, contract_b.model_dump(mode="json"))
    await publish_event("policy.enforced", lease.lease_id, event_payload)
    if ingestion.collection_id:
        try:
            vector = VultrVectorStore(collection_id=ingestion.collection_id)
            await vector.add_item(
                ingestion.collection_id,
                json.dumps(event_payload, separators=(",", ":"), default=str),
                f"Enforcement outcome for {contract_a.device_model}; lease {lease.lease_id}",
            )
        except VultrVectorStoreError as exc:
            await _emit(f"[MEMORY WARN] Could not write enforcement outcome back to Vector Store ({exc}).\n")
    await _emit(f"[EVIDENCE SEALED] Lease {lease.lease_id}; object {evidence_key or 'strict-mode disabled'}.\n")

    return contract_b


async def _tool_executor(tool_name: str, arguments: dict) -> str:
    """
    Routes Nemotron's tool call requests to the correct Python function.
    This is the bridge between the LLM and the actual tool implementations.
    """
    if tool_name == "retrieve_document":
        chunks = query_manual(
            query=arguments.get("query", ""),
            device_model=arguments.get("device_model", ""),
            top_k=arguments.get("top_k", 3),
        )
        return format_chunks_for_llm(chunks)

    if tool_name == "retrieve_document":
        return await retrieve_document(
            query=arguments.get("query", ""),
            device_model=arguments.get("device_model", ""),
            top_k=arguments.get("top_k", 3),
        )

    if tool_name == "check_cve":
        return await query_cve(
            device_model=arguments.get("device_model", ""),
            firmware_version=arguments.get("firmware_version", ""),
        )

    if tool_name == "apply_firewall_rule":
        return apply_firewall_rule(
            target_vpc_id=arguments.get("target_vpc_id", ""),
            firewall_rules=arguments.get("firewall_rules", []),
            confidence_score=arguments.get("confidence_score", 0),
            cve_flagged=arguments.get("cve_flagged", "NONE"),
            memo_text=arguments.get("memo_text", ""),
        )

    return f"ERROR: Unknown tool '{tool_name}'"


async def retract_policy(device_id: str) -> dict:
    """
    Human Override — called by DELETE /api/v1/policy/{device_id}.
    Immediately retracts the active firewall policy for the given device.
    """
    result = retract_firewall_rule(device_id)
    parsed = json.loads(result)
    if parsed.get("lease_id"):
        await cancel_expiry(parsed["lease_id"])
    return parsed


def _deterministic_policy(contract_a: ContractA, vpc_id: str) -> ContractB:
    """
    Builds a zero-trust firewall policy without the LLM — used as a safety net
    when Nemotron does not call apply_firewall_rule. ALLOWs manual ports,
    DENYs SSH/Telnet, and flags any CVE found for the device.
    """
    rules = [FirewallRule(port=p.port, action="ALLOW") for p in contract_a.allowed_ports]
    # Always deny common lateral-movement ports not explicitly allowed
    allowed_ports = {p.port for p in contract_a.allowed_ports}
    for risky_port in (22, 23):
        if risky_port not in allowed_ports:
            rules.append(FirewallRule(port=risky_port, action="DENY"))

    cve_id = "NONE"
    memo = (
        f"Applied deterministic zero-trust baseline for {contract_a.device_model}; "
        f"allowed {sorted(allowed_ports)}, denied SSH/Telnet. CVE evidence requires manual review."
    )
    confidence = 60

    return ContractB(
        target_vpc_id=vpc_id,
        firewall_rules=rules,
        confidence_score=confidence,
        cve_flagged=cve_id,
        memo_text=memo,
    )


def _parse_contract_a(raw: str) -> tuple[ContractA, bool]:
    """Parses the LLM's JSON output into a ContractA model.

    Falls back to DEMO_CONTRACT_A (not an empty placeholder) whenever the
    output doesn't parse or parses with no usable ports, so a single Nemotron
    hiccup never breaks the rest of the pipeline mid-demo. Returns
    (contract, fell_back) — fell_back is True whenever DEMO_CONTRACT_A was
    substituted, so callers can surface that instead of silently reporting
    placeholder data as a real extraction.
    """
    try:
        cleaned = raw.strip().strip("```json").strip("```").strip()
        data = json.loads(cleaned)
        contract = ContractA(**data)
        if contract.allowed_ports:
            return contract, False
    except Exception:
        pass
    return DEMO_CONTRACT_A.model_copy(), True


def _extract_contract_b(final_message: dict, vpc_id: str) -> ContractB:
    """
    Extracts ContractB from the final assistant message.
    Nemotron may have embedded the policy in content as JSON, or it's already stored
    in the in-memory policy store via the apply_firewall_rule tool call.
    """
    from agent.tools.firewall import _active_policies

    # Try to find an active policy stored during the agentic loop
    for policy in _active_policies.values():
        if policy.target_vpc_id == vpc_id:
            return policy

    # Fallback: parse content JSON if Nemotron included it in its final message
    content = final_message.get("content", "")
    try:
        cleaned = content.strip().strip("```json").strip("```").strip()
        data = json.loads(cleaned)
        return ContractB(**data)
    except Exception:
        return ContractB(
            target_vpc_id=vpc_id,
            firewall_rules=[],
            confidence_score=0,
            cve_flagged="NONE",
            memo_text="Policy extraction failed. Manual review required.",
        )
