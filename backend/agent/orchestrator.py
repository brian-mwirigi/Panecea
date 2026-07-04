# Core 7-step agent loop. Coordinates extraction → CVE check → policy decision → firewall enforcement → memo generation.

import json
import sys
from pathlib import Path
from typing import Awaitable, Callable

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent.prompts import TOOLS, agentic_policy_prompt, extraction_prompt, incident_memo_prompt
from agent.tools.cve_lookup import format_for_llm, mock_cve_lookup
from agent.tools.firewall import apply_firewall_rule, retract_firewall_rule
from schemas.contract_a import ContractA
from schemas.contract_b import ContractB, FirewallRule
from services.vultr_inference import StreamToken, complete, run_agentic_loop
from services.vultr_vector import ingest_manual


async def run_pipeline(
    raw_pdf_text: str,
    vpc_id: str,
    on_token: Callable[[StreamToken], Awaitable[None]] | None = None,
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
    contract_a = _parse_contract_a(extraction_raw)
    await _emit(f"[STEP 2 DONE] Device: {contract_a.device_model} | Firmware: {contract_a.firmware_version} | Ports: {[p.port for p in contract_a.allowed_ports]}\n")

    # ------------------------------------------------------------------
    # Step 3 + 4 + 6: Nemotron autonomously calls tools to CVE check,
    # decide policy, and apply firewall rules
    # ------------------------------------------------------------------
    await _emit("\n[STEP 3-4-6] Handing control to Nemotron for CVE check, policy decision, and firewall enforcement...\n")

    messages = agentic_policy_prompt(
        device_model=contract_a.device_model,
        firmware_version=contract_a.firmware_version,
        allowed_ports=[p.model_dump() for p in contract_a.allowed_ports],
        vpc_id=vpc_id,
    )

    final_message = await run_agentic_loop(
        messages=messages,
        tools=TOOLS,
        tool_executor=_tool_executor,
        on_token=on_token,
    )

    # ------------------------------------------------------------------
    # Step 5: Store the extracted manual in Vultr Vector Store
    # ------------------------------------------------------------------
    await _emit("\n[STEP 5] Chunking manual and storing Contract A in Vultr Vector Store...\n")
    try:
        ingestion = await ingest_manual(raw_pdf_text, contract_a)
        contract_a = contract_a.model_copy(update={"source_doc_id": ingestion.source_doc_id})
        await _emit(
            f"[STEP 5 DONE] Stored {ingestion.chunk_count} chunks in Vultr collection "
            f"{ingestion.collection_id}; source vector {ingestion.source_doc_id}.\n"
        )
    except Exception as e:
        await _emit(f"[STEP 5 WARN] Vector store unavailable — continuing without storage: {e}\n")

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

    return contract_b


def _tool_executor(tool_name: str, arguments: dict) -> str:
    """
    Routes Nemotron's tool call requests to the correct Python function.
    This is the bridge between the LLM and the actual tool implementations.
    """
    if tool_name == "check_cve":
        result = mock_cve_lookup(
            device_model=arguments.get("device_model", ""),
            firmware_version=arguments.get("firmware_version", ""),
        )
        return format_for_llm(result)

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
    return json.loads(result)


def _deterministic_policy(contract_a: ContractA, vpc_id: str) -> ContractB:
    """
    Builds a zero-trust firewall policy without the LLM — used as a safety net
    when Nemotron does not call apply_firewall_rule. ALLOWs manual ports,
    DENYs SSH/Telnet, and flags any CVE found for the device.
    """
    cve = mock_cve_lookup(contract_a.device_model, contract_a.firmware_version)

    rules = [FirewallRule(port=p.port, action="ALLOW") for p in contract_a.allowed_ports]
    # Always deny common lateral-movement ports not explicitly allowed
    allowed_ports = {p.port for p in contract_a.allowed_ports}
    for risky_port in (22, 23):
        if risky_port not in allowed_ports:
            rules.append(FirewallRule(port=risky_port, action="DENY"))

    cve_id = cve["cve_id"]
    if cve_id != "NONE":
        memo = (
            f"Blocked lateral movement on ports 22/23 for {contract_a.device_model}. "
            f"Flagged {cve_id} ({cve['severity']}). Allowed manual-approved ports {sorted(allowed_ports)}."
        )
        confidence = 88
    else:
        memo = (
            f"Applied zero-trust baseline for {contract_a.device_model}. "
            f"Allowed {sorted(allowed_ports)}, denied SSH/Telnet."
        )
        confidence = 82

    return ContractB(
        target_vpc_id=vpc_id,
        firewall_rules=rules,
        confidence_score=confidence,
        cve_flagged=cve_id,
        memo_text=memo,
    )


def _parse_contract_a(raw: str) -> ContractA:
    """Parses the LLM's JSON output into a ContractA model. Falls back to a safe default on failure."""
    try:
        cleaned = raw.strip().strip("```json").strip("```").strip()
        data = json.loads(cleaned)
        return ContractA(**data)
    except Exception:
        return ContractA(
            device_model="Unknown_Device",
            firmware_version="unknown",
            allowed_ports=[],
            source_doc_id="",
        )


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
