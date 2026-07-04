###  PANACEA


**Contract A: Extraction Output ➔ Vultr Vector Store**

```json
{
  "device_model": "Philips_IntelliVue",
  "firmware_version": "B.01",
  "allowed_ports": [
    {"port": 3200, "protocol": "TCP", "reason": "HL7 Patient Data"}
  ],
  "source_doc_id": "vultr_vector_id_12345"
}

```

**Contract B: Agent Decision ➔ Firewall API / Incident Memo**

```json
{
  "target_vpc_id": "vpc-medical-01",
  "firewall_rules": [
    {"port": 3200, "action": "ALLOW"},
    {"port": 22, "action": "DENY"}
  ],
  "confidence_score": 96,
  "cve_flagged": "CVE-2023-XXXX",
  "memo_text": "Blocked lateral pivot on Port 22. Allowed Port 3200 per Vector ID: 12345."
}

```

---

###  THE FINAL DIVISION

**1. Zain – Threat Execution & Security Infra**

* **The Task:** You own the Python Firewall execution scripts and the attacker VM.
* **The Rule:** *The Hour-14 Checkpoint.* Getting the live attacker VM to trigger the live Vultr Firewall lockdown is the highest-risk piece of this hackathon. You and Mohamed must test this handoff first. If it is unstable by hour 14, we drop the live VMs and fallback to a hardcoded/scripted anomaly event for the demo.

**2. Goutham – The Memory Engine (Vultr Vector Store)**

* **The Task:** You own the ingestion pipeline, but **do not use ChromaDB or Qdrant.** We use **Vultr Vector Store** exclusively to keep the "no substitutions" pitch alive. You chunk the manual and push it using Contract A.

**3. Oleh – The Command Center (Next.js UI)**

* **The Task:** You own the Next.js frontend, the WebSocket terminal, and the "Human Override" toggle.
* **The Addition:** You will also parse Contract B to display the formal "Incident Memo" on the UI so we nail that enterprise feel.

**4. Mohamed – IIoT Target & Manual Sourcing**

* **The Task:** Set up the Philips VM target for Zain.
* **The Addition:** You explicitly own sourcing the actual Philips IntelliVue PDF manual and finding the exact page that mentions Port 3200 so we have our demo prop ready.

**5. Brian – Agent Orchestration (Core + Stretch)**

* **The Task:** Build the Vultr Serverless Inference agent loop and tie our modules together.
* **The Stretch:** Own the v2 differentiators (CVE mock cross-check, confidence scoring, and memo generation). If time runs short, I will cut these first to ensure the core firewall loop survives.
