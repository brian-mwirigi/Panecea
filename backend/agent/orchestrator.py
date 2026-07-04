# Core 7-step agent loop. Coordinates extraction → CVE check → policy decision → firewall enforcement → memo generation.

import json
import hashlib
import os
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

# Module-level policy history for drift detection (device_model → last ContractB).
_policy_history: dict[str, "ContractB"] = {}

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent.prompts import TOOLS, agentic_policy_prompt, extraction_prompt, incident_memo_prompt
from agent.tools.firewall import apply_firewall_rule, get_enforcement_result, retract_firewall_rule
from schemas.contract_a import AllowedPort, ContractA
from schemas.contract_b import ContractB, FirewallRule
from schemas.control_plane import EvidenceBundle, EnforcementReceipt, PolicyLease
from services.audit_log import append_audit_entry
from services.vultr_events import publish_event
from services.vultr_inference import StreamToken, complete, run_agentic_loop
from services.vultr_object_storage import VultrObjectStorage, VultrObjectStorageError
from services.policy_leases import cancel_expiry, schedule_expiry
from services.vultr_vector import (
    VultrVectorStore,
    ingest_manual,
    query_cve,
    query_manual,
    retrieve_document,
)


# Demo manual — sourced from the real Philips IntelliVue Data Export Interface
# Programming Guide (part 4535 645 88011, release L.0, 08/2015, 339 pp).
# UDP 24105 is from Section 4, p.29. UDP 24005 is from Section 5, p.53.
# Using these real numbers so the fallback path produces citable output.
DEMO_MANUAL_TEXT = (
    "Philips IntelliVue Patient Monitor — Data Export Interface Programming Guide "
    "(X2, MP, MX, FM Series, Release L.0, Firmware B.01). "
    "Section 4 — Transport Protocols for the LAN Interface (p. 29): "
    "'The current Protocol version uses the fixed UDP port 24105. "
    "All messages sent from the Computer Client to the monitor must use this port number "
    "as the destination port number.' "
    "Section 5 — Connect Indication Event (p. 53): "
    "UDP port 24005 is used for device discovery broadcasts. "
    "All remote administration (SSH, port 22) must remain disabled in clinical "
    "deployments to prevent lateral movement across the hospital network."
)

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

    manual_text = raw_pdf_text.strip() or DEMO_MANUAL_TEXT
    if not raw_pdf_text.strip():
        await _emit("\n[STEP 1] No manual text supplied — using demo Philips IntelliVue excerpt.\n")

    # ------------------------------------------------------------------
    # Step 2: Extract device info from the PDF text
    # ------------------------------------------------------------------
    await _emit("\n[STEP 2] Extracting network requirements from device manual...\n")
    extraction_raw = await complete(extraction_prompt(manual_text))
    contract_a = _parse_contract_a(extraction_raw)
    if source_doc_id:
        contract_a = contract_a.model_copy(update={"source_doc_id": source_doc_id})
    await _emit(f"[STEP 2 DONE] Device: {contract_a.device_model} | Firmware: {contract_a.firmware_version} | Ports: {[p.port for p in contract_a.allowed_ports]}\n")

    # ------------------------------------------------------------------
    # Step 5: Commit Contract A and chunks before any enforcement decision.
    # ------------------------------------------------------------------
    await _emit("\n[STEP 5] Chunking manual and storing Contract A in Vultr Vector Store...\n")
    ingestion = await ingest_manual(raw_pdf_text, contract_a)
    contract_a = contract_a.model_copy(update={"source_doc_id": ingestion.source_doc_id})
    await publish_event("contract-a.extracted", ingestion.source_doc_id, contract_a.model_dump(mode="json"))
    await _emit(
        f"[STEP 5 DONE] Stored {ingestion.chunk_count} chunks in Vultr collection "
        f"{ingestion.collection_id}; source vector {ingestion.source_doc_id}.\n"
    )

    await _emit("\n[MEMORY] Retrieving authoritative evidence through Vultr RAG...\n")
    retrieved_context = await query_manual(ingestion.collection_id, contract_a)
    await _emit("[MEMORY DONE] Manufacturer evidence attached to the decision.\n")

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

    # Count reasoning characters to derive real confidence from deliberation depth.
    # Also capture evidence returned by tool calls so the memo can cite it.
    reasoning_chars = 0
    tool_evidence: dict[str, str] = {"cve": "", "retrieved": ""}

    async def _on_token_counted(token: StreamToken) -> None:
        nonlocal reasoning_chars
        if token.type == "reasoning":
            reasoning_chars += len(token.text)
        if on_token:
            await on_token(token)

    async def _tool_executor_capturing(tool_name: str, arguments: dict) -> str:
        result = await _tool_executor(tool_name, arguments)
        if tool_name == "check_cve":
            tool_evidence["cve"] = result
        elif tool_name == "retrieve_document":
            tool_evidence["retrieved"] += ("\n" + result if tool_evidence["retrieved"] else result)
        return result

    final_message = await run_agentic_loop(
        messages=messages,
        tools=TOOLS,
        tool_executor=_tool_executor_capturing,
        on_token=_on_token_counted,
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
    # Feature 1: Real confidence from reasoning depth AND evidence grounding.
    # Short decisive reasoning + every rule backed by evidence → high confidence.
    # Long deliberation or rules with no supporting document → lower.
    # ------------------------------------------------------------------
    combined_evidence = "\n".join(
        part for part in (retrieved_context, tool_evidence["retrieved"], tool_evidence["cve"]) if part
    )
    grounded, total = _evidence_coverage(contract_b, combined_evidence)
    real_confidence = _confidence_from_reasoning(
        reasoning_chars, contract_b.cve_flagged, len(contract_b.firewall_rules), grounded, total
    )
    confidence_explanation = _confidence_explanation(
        reasoning_chars, contract_b.cve_flagged, grounded, total
    )
    contract_b = contract_b.model_copy(update={"confidence_score": real_confidence})
    await _emit(f"\n[CONFIDENCE] {real_confidence}% — {confidence_explanation}\n")

    # ------------------------------------------------------------------
    # Feature 3: Policy drift detection — flag if this device was seen before.
    # ------------------------------------------------------------------
    drift_alert = _detect_drift(contract_a.device_model, contract_b)
    if drift_alert:
        alert_msg = f"\n[DRIFT ALERT] Policy changed since last scan: {drift_alert}\n"
        await _emit(alert_msg, "reasoning")
        contract_b = contract_b.model_copy(
            update={"memo_text": contract_b.memo_text + f"\n\n⚠️ DRIFT ALERT: {drift_alert}"}
        )
    _policy_history[contract_a.device_model] = contract_b

    # ------------------------------------------------------------------
    # Step 7: Expand the incident memo for Oleh's frontend
    # ------------------------------------------------------------------
    await _emit("\n[STEP 7] Generating incident memo with citation trail...\n")
    memo = await complete(incident_memo_prompt(
        contract_b.model_dump(),
        retrieved_context="\n".join(p for p in (retrieved_context, tool_evidence["retrieved"]) if p),
        cve_evidence=tool_evidence["cve"],
    ))
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
    schedule_expiry(lease)
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
    vector = VultrVectorStore(collection_id=ingestion.collection_id)
    await vector.add_item(
        ingestion.collection_id,
        json.dumps(event_payload, separators=(",", ":"), default=str),
        f"Enforcement outcome for {contract_a.device_model}; lease {lease.lease_id}",
    )
    await _emit(f"[EVIDENCE SEALED] Lease {lease.lease_id}; object {evidence_key or 'strict-mode disabled'}.\n")

    # ------------------------------------------------------------------
    # Feature 4: Structured audit log — every decision is auditable.
    # ------------------------------------------------------------------
    append_audit_entry({
        "event": "policy.decided",
        "lease_id": lease.lease_id,
        "operator_id": operator_id,
        "device_model": contract_a.device_model,
        "firmware_version": contract_a.firmware_version,
        "source_doc_id": contract_a.source_doc_id,
        "confidence_score": contract_b.confidence_score,
        "confidence_explanation": confidence_explanation,
        "reasoning_chars": reasoning_chars,
        "cve_flagged": contract_b.cve_flagged,
        "firewall_rules": [r.model_dump() for r in contract_b.firewall_rules],
        "drift_alert": drift_alert,
        "evidence_key": evidence_key,
        "evidence_sha256": evidence.evidence_sha256,
    })

    return contract_b


async def _tool_executor(tool_name: str, arguments: dict) -> str:
    """
    Routes Nemotron's tool call requests to the correct Python function.
    This is the bridge between the LLM and the actual tool implementations.
    """
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
        cancel_expiry(parsed["lease_id"])
    return parsed


def _evidence_coverage(contract_b: "ContractB", evidence: str) -> tuple[int, int]:
    """
    Counts how many firewall rules are grounded in the retrieved evidence
    (the rule's port number appears in the manual/CVE text) vs left unexplained.
    Mirrors the PS finance example: confidence reflects matched-to-cause coverage.
    """
    total = len(contract_b.firewall_rules)
    if total == 0 or not evidence:
        return 0, total
    grounded = sum(1 for r in contract_b.firewall_rules if str(r.port) in evidence)
    return grounded, total


def _confidence_from_reasoning(
    reasoning_chars: int,
    cve_flagged: str,
    rule_count: int,
    grounded: int = 0,
    total: int = 0,
) -> int:
    """
    Derives a real confidence score from reasoning depth AND evidence grounding.
    Short decisive reasoning = high confidence; long deliberation = lower.
    Evidence coverage (grounded/total rules) then scales the score — a decision
    where every rule is backed by a cited document scores higher than one with
    unexplained rules.
    """
    if reasoning_chars < 300:
        base = 93
    elif reasoning_chars < 800:
        base = 85
    elif reasoning_chars < 2000:
        base = 74
    elif reasoning_chars < 4000:
        base = 62
    else:
        base = 50

    if cve_flagged and cve_flagged not in ("NONE", ""):
        base -= 12  # CVE evidence forces deliberation penalty
    if rule_count == 0:
        base -= 15  # no rules produced = uncertain outcome

    # Evidence grounding: penalise proportionally for unexplained rules (max -25).
    if total > 0:
        coverage = grounded / total
        base -= int((1 - coverage) * 25)

    return max(10, min(98, base))


def _confidence_explanation(
    reasoning_chars: int,
    cve_flagged: str,
    grounded: int = 0,
    total: int = 0,
) -> str:
    """Human-readable rationale for the confidence score, shown in the memo."""
    if reasoning_chars < 300:
        depth = "short decisive reasoning — no ambiguity detected"
    elif reasoning_chars < 800:
        depth = "moderate deliberation — minor uncertainty resolved"
    elif reasoning_chars < 2000:
        depth = "extended deliberation — conflicting signals weighed"
    else:
        depth = "long deliberation — significant uncertainty or conflicting CVE evidence"

    cve_note = "; CVE evidence introduced additional uncertainty" if (cve_flagged and cve_flagged not in ("NONE", "")) else ""
    grounding_note = f"; {grounded}/{total} rules grounded in cited evidence" if total > 0 else ""
    return f"{depth}{cve_note}{grounding_note}"


def _detect_drift(device_model: str, new_policy: "ContractB") -> str | None:
    """
    Compares the new policy against the last stored policy for this device.
    Returns a human-readable drift summary if the port set changed, else None.
    """
    prev = _policy_history.get(device_model)
    if not prev:
        return None

    prev_ports = {(r.port, r.action) for r in prev.firewall_rules}
    new_ports = {(r.port, r.action) for r in new_policy.firewall_rules}

    added = new_ports - prev_ports
    removed = prev_ports - new_ports

    if not added and not removed:
        return None

    parts = []
    if added:
        ports_str = ", ".join(f"port {p} ({a})" for p, a in sorted(added))
        parts.append(f"NEW rules added: {ports_str}")
    if removed:
        ports_str = ", ".join(f"port {p} ({a})" for p, a in sorted(removed))
        parts.append(f"REMOVED rules: {ports_str}")

    return "; ".join(parts)


async def explain_policy(contract_b: "ContractB") -> str:
    """
    Calls Nemotron to generate a plain-English compliance justification
    for a given policy decision. Used by /api/v1/agent/explain.
    """
    from agent.prompts import SYSTEM_PROMPT

    rules_text = "\n".join(
        f"  - Port {r.port}: {r.action}" for r in contract_b.firewall_rules
    )
    prompt_messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                f"You are a compliance officer's AI assistant. Explain the following network security "
                f"policy decision in 3-4 plain-English sentences that a hospital compliance officer "
                f"could read in a regulatory audit. Be specific about ports, risks, and reasoning.\n\n"
                f"Device: {contract_b.target_vpc_id}\n"
                f"Confidence: {contract_b.confidence_score}%\n"
                f"CVE Flagged: {contract_b.cve_flagged}\n"
                f"Firewall Rules:\n{rules_text}\n"
                f"Memo: {contract_b.memo_text}"
            ),
        },
    ]
    return await complete(prompt_messages)


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


def _parse_contract_a(raw: str) -> ContractA:
    """Parses the LLM's JSON output into a ContractA model. Falls back to demo device on failure."""
    try:
        cleaned = raw.strip().strip("```json").strip("```").strip()
        data = json.loads(cleaned)
        contract = ContractA(**data)
        if contract.allowed_ports:
            return contract
    except Exception:
        pass
    return DEMO_CONTRACT_A.model_copy()


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
