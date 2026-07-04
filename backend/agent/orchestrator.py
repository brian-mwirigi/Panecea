# Core 7-step agent loop. Coordinates extraction → CVE check → policy decision → firewall enforcement → memo generation.

import json
import sys
from pathlib import Path
from typing import AsyncGenerator, Callable

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from agent.prompts import TOOLS, agentic_policy_prompt, extraction_prompt, incident_memo_prompt
from agent.tools.cve_lookup import format_for_llm, mock_cve_lookup
from agent.tools.firewall import apply_firewall_rule, retract_firewall_rule
from schemas.contract_a import ContractA
from schemas.contract_b import ContractB
from services.vultr_inference import StreamToken, complete, run_agentic_loop, stream_completion


async def run_pipeline(
    raw_pdf_text: str,
    vpc_id: str,
    on_token: Callable[[StreamToken], None] | None = None,
) -> ContractB:
    """
    Executes the full 7-step PANACEA pipeline.

    Steps:
        1. Ingest      — raw_pdf_text arrives from Goutham's PDF module
        2. Extract     — LLM pulls device model, firmware, allowed ports (Contract A)
        3. CVE Check   — Nemotron autonomously calls check_cve tool
        4. Decide      — Nemotron generates zero-trust policy (Contract B)
        5. Store       — stubbed (Goutham's vector store module)
        6. Enforce     — Nemotron calls apply_firewall_rule tool
        7. Report      — LLM expands memo for the frontend

    Args:
        raw_pdf_text: Raw text extracted from the medical device PDF.
        vpc_id: Target Vultr VPC ID (e.g. "vpc-medical-01").
        on_token: Optional WebSocket callback — receives StreamToken on each reasoning/content chunk.

    Returns:
        ContractB with the final firewall policy and incident memo.
    """

    def _emit(text: str, token_type: str = "reasoning") -> None:
        if on_token:
            on_token(StreamToken(text=text, type=token_type))

    # ------------------------------------------------------------------
    # Step 2: Extract device info from the PDF text
    # ------------------------------------------------------------------
    _emit("\n[STEP 2] Extracting network requirements from device manual...\n")
    extraction_raw = await complete(extraction_prompt(raw_pdf_text))
    contract_a = _parse_contract_a(extraction_raw)
    _emit(f"[STEP 2 DONE] Device: {contract_a.device_model} | Firmware: {contract_a.firmware_version} | Ports: {[p.port for p in contract_a.allowed_ports]}\n")

    # ------------------------------------------------------------------
    # Step 3 + 4 + 6: Nemotron autonomously calls tools to CVE check,
    # decide policy, and apply firewall rules
    # ------------------------------------------------------------------
    _emit("\n[STEP 3-4-6] Handing control to Nemotron for CVE check, policy decision, and firewall enforcement...\n")

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
    # Step 5: Store policy to vector store (stubbed — Goutham's module)
    # ------------------------------------------------------------------
    _emit("\n[STEP 5] Storing policy to Vultr Vector Store... [STUB — pending Goutham's module]\n")

    # ------------------------------------------------------------------
    # Extract ContractB from the last apply_firewall_rule tool call
    # ------------------------------------------------------------------
    contract_b = _extract_contract_b(final_message, vpc_id)

    # ------------------------------------------------------------------
    # Step 7: Expand the incident memo for Oleh's frontend
    # ------------------------------------------------------------------
    _emit("\n[STEP 7] Generating incident memo...\n")
    memo = await complete(incident_memo_prompt(contract_b.model_dump()))
    contract_b.memo_text = memo.strip()
    _emit(f"\n[STEP 7 DONE] Memo ready.\n", "content")

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
