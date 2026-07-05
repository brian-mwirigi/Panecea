import unittest

from agent.orchestrator import _parse_contract_a


class ParseContractATests(unittest.TestCase):
    def test_valid_json_does_not_fall_back(self) -> None:
        raw = """```json
        {
          "device_model": "Philips_IntelliVue",
          "firmware_version": "B.01",
          "allowed_ports": [{"port": 3200, "protocol": "TCP", "reason": "HL7"}],
          "source_doc_id": ""
        }
        ```"""
        contract, fell_back = _parse_contract_a(raw)
        self.assertFalse(fell_back)
        self.assertEqual(contract.device_model, "Philips_IntelliVue")

    def test_unparseable_output_signals_fallback(self) -> None:
        contract, fell_back = _parse_contract_a("Nemotron rambled instead of returning JSON.")
        self.assertTrue(fell_back)
        self.assertEqual(contract.device_model, "Unknown_Device")


if __name__ == "__main__":
    unittest.main()
