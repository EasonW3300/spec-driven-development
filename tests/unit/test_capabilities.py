from spec_driven.capabilities import Capability, CapabilityReport


def test_capability_report_serializes_stable_fields() -> None:
    report = CapabilityReport(1, "generic", "0.1.0", (Capability("confirmation", "available", "CLI", "exact command", None),))
    assert report.to_dict()["capabilities"][0]["status"] == "available"
