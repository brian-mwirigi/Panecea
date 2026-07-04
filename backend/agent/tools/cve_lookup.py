# mock_cve_lookup() tool. Returns a hardcoded CVE payload for a given device model + firmware string. No live NVD calls.

CVE_DATABASE = {
    "philips_intellivue": {
        "B.01": {
            "cve_id": "CVE-2023-40559",
            "severity": "HIGH",
            "cvss_score": 8.1,
            "description": "Philips IntelliVue firmware B.01 exposes an unauthenticated SMB service on port 445, allowing remote lateral movement across hospital subnets.",
            "affected_ports": [445, 22],
        },
        "default": {
            "cve_id": "CVE-2022-31479",
            "severity": "MEDIUM",
            "cvss_score": 6.5,
            "description": "Philips IntelliVue unpatched firmware allows unauthorized SSH access on port 22 due to a hardcoded default credential vulnerability.",
            "affected_ports": [22],
        },
    },
    "philips_lumify": {
        "default": {
            "cve_id": "CVE-2021-33895",
            "severity": "CRITICAL",
            "cvss_score": 9.3,
            "description": "Philips Lumify exposes a Telnet interface on port 23 with no authentication, enabling full remote command execution.",
            "affected_ports": [23, 22],
        },
    },
    "ge_mac5500": {
        "default": {
            "cve_id": "CVE-2023-27457",
            "severity": "HIGH",
            "cvss_score": 7.8,
            "description": "GE MAC 5500 ECG sends unencrypted patient data over port 2575 (HL7 v2), susceptible to network interception.",
            "affected_ports": [2575],
        },
    },
}

NO_CVE_RESULT = {
    "cve_id": "NONE",
    "severity": "LOW",
    "cvss_score": 0.0,
    "description": "No known CVEs found for this device model and firmware version.",
    "affected_ports": [],
}


def mock_cve_lookup(device_model: str, firmware_version: str) -> dict:
    """
    Returns a CVE payload for the given device model and firmware version.
    Used as the tool_executor target when Nemotron calls check_cve().
    """
    key = device_model.lower().replace(" ", "_").replace("-", "_")
    device_entry = CVE_DATABASE.get(key)

    if not device_entry:
        return NO_CVE_RESULT

    result = device_entry.get(firmware_version) or device_entry.get("default") or NO_CVE_RESULT
    return result


def format_for_llm(cve_result: dict) -> str:
    """Formats the CVE result into a string Nemotron can reason about."""
    if cve_result["cve_id"] == "NONE":
        return "No CVEs found. Device firmware appears clean."

    return (
        f"CVE ID: {cve_result['cve_id']}\n"
        f"Severity: {cve_result['severity']} (CVSS {cve_result['cvss_score']})\n"
        f"Description: {cve_result['description']}\n"
        f"Affected ports: {cve_result['affected_ports']}"
    )
