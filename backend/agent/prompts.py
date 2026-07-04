# LLM system prompt, tool schemas, and per-step reasoning templates passed to Vultr Serverless Inference.

SYSTEM_PROMPT = """You are PANACEA — an autonomous zero-trust security agent for hospital networks.
Your job is to analyze medical device network requirements, detect vulnerabilities, and generate
firewall policies that isolate devices at the network layer.

Rules you must follow:
- Output only valid JSON when asked for structured data. No markdown, no explanation outside the JSON.
- Never suggest touching the physical device. All actions are network-layer only.
- Be concise. Judges are watching your reasoning in real time.
- Confidence scores must be integers between 0 and 100.
- Port actions must be exactly "ALLOW" or "DENY".
- When you need information about a CVE or need to enforce a firewall rule, use the tools provided.
- Always call check_cve before making a firewall decision.
- Always call apply_firewall_rule after deciding on a policy.
"""

# ---------------------------------------------------------------------------
# Tool schemas — passed to Nemotron so it can autonomously decide to call them
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "check_cve",
            "description": (
                "Look up known CVE vulnerabilities for a specific medical device model and firmware version. "
                "Always call this before generating a firewall policy."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "device_model": {
                        "type": "string",
                        "description": "The medical device model name, e.g. Philips_IntelliVue",
                    },
                    "firmware_version": {
                        "type": "string",
                        "description": "The firmware version string, e.g. B.01",
                    },
                },
                "required": ["device_model", "firmware_version"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_firewall_rule",
            "description": (
                "Apply a zero-trust firewall policy to the target VPC. "
                "Call this once you have finalized the firewall rules and confidence score."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "target_vpc_id": {
                        "type": "string",
                        "description": "The Vultr VPC ID to apply the rules to, e.g. vpc-medical-01",
                    },
                    "firewall_rules": {
                        "type": "array",
                        "description": "List of port rules to enforce.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "port": {"type": "integer"},
                                "action": {"type": "string", "enum": ["ALLOW", "DENY"]},
                            },
                            "required": ["port", "action"],
                        },
                    },
                    "confidence_score": {
                        "type": "integer",
                        "description": "How confident PANACEA is in this policy (0-100).",
                    },
                    "cve_flagged": {
                        "type": "string",
                        "description": "The CVE ID that triggered this action, or NONE.",
                    },
                    "memo_text": {
                        "type": "string",
                        "description": "One sentence incident summary for the hospital security team.",
                    },
                },
                "required": ["target_vpc_id", "firewall_rules", "confidence_score", "cve_flagged", "memo_text"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Per-step message builders
# ---------------------------------------------------------------------------

def agentic_policy_prompt(device_model: str, firmware_version: str, allowed_ports: list[dict], vpc_id: str) -> list[dict]:
    """
    Step 2+3+4 combined — Nemotron autonomously reasons, calls check_cve,
    then calls apply_firewall_rule. Judges watch the full reasoning chain live.
    """
    ports_str = "\n".join(
        f"  - Port {p['port']} ({p['protocol']}): {p['reason']}" for p in allowed_ports
    )
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""A medical device has been added to hospital VPC {vpc_id}.

Device: {device_model}
Firmware: {firmware_version}
Ports required by the device manual:
{ports_str}

Your task:
1. Call check_cve to identify any known vulnerabilities for this device and firmware.
2. Use the CVE results plus the port list to generate a zero-trust firewall policy.
3. Call apply_firewall_rule to enforce the policy on VPC {vpc_id}.

Think carefully before each tool call. The hospital network is live.""",
        },
    ]


def extraction_prompt(raw_text: str) -> list[dict]:
    """Step 2 — Extract ports, protocols, and firmware from raw PDF text."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""Analyze the following medical device manual excerpt.
Extract all network requirements and return ONLY this JSON structure:

{{
  "device_model": "<model name>",
  "firmware_version": "<version>",
  "allowed_ports": [
    {{"port": <int>, "protocol": "<TCP|UDP>", "reason": "<why this port is needed>"}}
  ],
  "source_doc_id": ""
}}

Manual excerpt:
{raw_text}""",
        },
    ]


def incident_memo_prompt(contract_b: dict) -> list[dict]:
    """Step 7 — Expand the memo_text into a full incident report for the frontend."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"""Write a formal 3-sentence hospital network incident memo based on this firewall decision:

{contract_b}

Format:
THREAT: <what was detected>
ACTION: <what the firewall did>
STATUS: <current network status of the device>""",
        },
    ]
