"""Unit tests for SteadyDev models."""

from steadydev.models import Finding, FindingCategory, ReviewPacket, ReviewResult


def test_finding_category_normalization() -> None:
    f1 = Finding(
        finding_id="f-1",
        category="evidence-backed mismatch",  # hyphenated string
        locator="src/auth.py:10",
        description="Redirect mismatch detected",
    )
    assert f1.category == FindingCategory.EVIDENCE_MISMATCH

    f2 = Finding(
        finding_id="f-2",
        category="unverified",
        locator="lib/ui.dart:20",
        description="No viewport check",
    )
    assert f2.category == FindingCategory.UNVERIFIED


def test_review_packet_serialization(sample_clean_packet: ReviewPacket) -> None:
    data = sample_clean_packet.model_dump()
    assert data["packet_id"] == "pkt-test-01"
    assert len(data["changed_files"]) == 1
    assert data["changed_files"][0]["path"] == "src/auth.py"

    # Round trip
    reconstructed = ReviewPacket.model_validate(data)
    assert reconstructed.packet_id == sample_clean_packet.packet_id


def test_review_result_defaults() -> None:
    result = ReviewResult(packet_id="pkt-1", status="clean")
    assert result.status == "clean"
    assert result.findings == []
    assert result.retired_finding_ids == []
