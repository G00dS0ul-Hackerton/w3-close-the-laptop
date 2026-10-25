"""Unit tests for deterministic checklist baseline."""

from steadydev.baseline import ChecklistBaseline
from steadydev.models import (
    ChangedFile,
    CheckReceipt,
    Finding,
    FindingCategory,
    FindingStatus,
    ReviewPacket,
)


def test_baseline_clean_case(sample_clean_packet: ReviewPacket) -> None:
    baseline = ChecklistBaseline()
    result = baseline.evaluate(sample_clean_packet)
    assert result.status == "clean"
    assert len(result.findings) == 0
    assert result.timing_ms["total_duration_ms"] < 20.0  # sub-millisecond execution
    assert "No gaps detected by the baseline's limited rules" in result.restart_note
    assert (
        "does not establish that all requirements were verified" in result.restart_note
    )


def test_baseline_failed_check_receipt() -> None:
    packet = ReviewPacket(
        packet_id="pkt-fail-1",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="repo",
        session_intention="Fix auth login logic",
        acceptance_criteria=["Tests pass"],
        changed_files=[ChangedFile(path="src/auth.py", diff="+fix\n")],
        check_receipts=[
            CheckReceipt(
                receipt_id="r-fail",
                command="pytest tests/test_auth.py",
                exit_code=1,
                output_summary="1 failed in 0.1s",
                timestamp_utc="2026-10-21T02:00:00Z",
            )
        ],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    assert result.status == "findings_detected"
    assert any(
        "Check execution failed with exit code 1" in f.description
        for f in result.findings
    )


def test_baseline_does_not_retire_on_unrelated_receipt() -> None:
    prior = Finding(
        finding_id="f-layout-01",
        category=FindingCategory.UNVERIFIED,
        locator="lib/widgets/nav_bar.dart:18",
        description="No check recorded for modified layout.",
        status=FindingStatus.OPEN,
    )
    packet = ReviewPacket(
        packet_id="pkt-unrelated-test",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="repo",
        session_intention="Refactor helper logic",
        acceptance_criteria=["Update helper"],
        changed_files=[ChangedFile(path="lib/helper.dart", diff="+code\n")],
        check_receipts=[
            CheckReceipt(
                receipt_id="r-unrelated",
                command="flutter test test/helper_test.dart",
                exit_code=0,
                output_summary="1 passed (helper logic only, no viewport checks)",
                timestamp_utc="2026-10-21T02:00:00Z",
            )
        ],
        prior_findings=[prior],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    # The unrelated helper test must NOT retire the layout finding!
    assert "f-layout-01" not in result.retired_finding_ids


def test_baseline_detects_missing_viewport_receipt() -> None:
    packet = ReviewPacket(
        packet_id="pkt-ui-1",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="ui-repo",
        session_intention="Adjust mobile navigation layout",
        acceptance_criteria=["Update mobile nav bar styling"],
        changed_files=[
            ChangedFile(
                path="lib/widgets/nav_bar.dart",
                diff="@@ -10,2 +10,2 @@\n-flex: 1\n+flex: 2\n",
            )
        ],
        check_receipts=[
            CheckReceipt(
                receipt_id="r1",
                command="flutter test test/unit_test.dart",
                exit_code=0,
                output_summary="All tests passed",
                timestamp_utc="2026-10-21T02:00:00Z",
            )
        ],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    assert result.status == "findings_detected"
    assert len(result.findings) == 1
    assert result.findings[0].category == FindingCategory.UNVERIFIED
    assert "No check recorded for modified layout" in result.findings[0].description


def test_baseline_respects_explicit_deferrals() -> None:
    packet = ReviewPacket(
        packet_id="pkt-def-1",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="repo",
        session_intention="Add profile UI. Deferring viewport test to tomorrow.",
        acceptance_criteria=["Profile widget created"],
        changed_files=[
            ChangedFile(path="lib/profile.dart", diff="+class Profile {}\n")
        ],
        check_receipts=[
            CheckReceipt(
                receipt_id="r1",
                command="pytest",
                exit_code=0,
                output_summary="ok",
                timestamp_utc="2026-10-21T02:00:00Z",
            )
        ],
        explicit_deferrals=["viewport test intentionally deferred to tomorrow"],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    # Viewport check finding suppressed because of explicit deferral
    assert result.status == "clean"
    assert len(result.findings) == 0


def test_baseline_dart_non_layout_not_flagged() -> None:
    """Dart utility files without layout elements must not trigger layout missing-check warnings."""
    packet = ReviewPacket(
        packet_id="pkt-dart-util",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="flutter-repo",
        session_intention="Update string util",
        acceptance_criteria=["Update trimName helper", "Unit tests pass"],
        changed_files=[
            ChangedFile(
                path="lib/utils/string_helper.dart",
                diff="@@ -5,3 +5,3 @@\n-String trimName(String s) => s.trim();\n+String trimName(String s) => s.trim().toLowerCase();\n",
            )
        ],
        check_receipts=[
            CheckReceipt(
                receipt_id="r1",
                command="flutter test test/string_helper_test.dart",
                exit_code=0,
                output_summary="1 passed in 0.2s",
                timestamp_utc="2026-10-21T02:00:00Z",
            )
        ],
    )
    baseline = ChecklistBaseline()
    res = baseline.evaluate(packet)
    # Utility dart file with test must NOT be flagged as missing viewport/layout checks!
    assert res.status == "clean"
    assert len(res.findings) == 0


def test_baseline_reconciles_prior_unverified_finding() -> None:
    prior = Finding(
        finding_id="f-old-99",
        category=FindingCategory.UNVERIFIED,
        locator="lib/nav.dart:1",
        description="No check recorded for modified layout.",
        status=FindingStatus.OPEN,
    )
    packet = ReviewPacket(
        packet_id="pkt-reconcile-1",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="repo",
        session_intention="Add viewport test",
        acceptance_criteria=["Verify layout"],
        changed_files=[
            ChangedFile(path="test/nav_viewport_test.dart", diff="+test()\n")
        ],
        check_receipts=[
            CheckReceipt(
                receipt_id="rcpt-vp",
                command="flutter test test/nav_viewport_test.dart",
                exit_code=0,
                output_summary="1 passed",
                timestamp_utc="2026-10-21T02:00:00Z",
            )
        ],
        prior_findings=[prior],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    assert "f-old-99" in result.retired_finding_ids


def test_baseline_is_blind_to_semantic_redirect_mismatch() -> None:
    """Proves baseline limitation: when code contradicts intent but tests pass, baseline passes."""
    packet = ReviewPacket(
        packet_id="pkt-mismatch-1",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="repo",
        session_intention="Redirect authenticated users to /dashboard",
        acceptance_criteria=["Redirect to /dashboard"],
        changed_files=[
            ChangedFile(
                path="src/views.py",
                diff="@@ -40,3 +40,3 @@\n-return redirect('/login')\n+return redirect('/home')\n",
            )
        ],
        check_receipts=[
            CheckReceipt(
                receipt_id="r1",
                command="pytest tests/test_views.py",
                exit_code=0,
                output_summary="1 passed (checked status 302)",
                timestamp_utc="2026-10-21T02:00:00Z",
            )
        ],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    # The baseline only sees: code changed, test passed -> reports clean!
    # This precisely proves why the open-source LLM is essential for semantic understanding.
    assert result.status == "clean"
    assert len(result.findings) == 0


def test_baseline_generates_intention_aware_restart_note_with_open_findings() -> None:
    """When open unverified findings exist, restart note explicitly names the gap and intention."""
    packet = ReviewPacket(
        packet_id="pkt-gap-1",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="sample-project",
        session_intention="Implement biometric login and fix auth tokens",
        acceptance_criteria=["Auth tests pass"],
        changed_files=[
            ChangedFile(
                path="src/auth.py", diff="@@ -1,3 +1,3 @@\n+def login(): pass\n"
            )
        ],
        check_receipts=[],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    assert result.status == "findings_detected"
    assert len(result.findings) > 0
    # Must NOT be the old generic static string
    assert result.restart_note != "Continue by addressing open unverified checks."
    # Must be intention-aware and mention the modified file or gap
    assert "src/auth.py" in result.restart_note
    assert (
        "biometric login" in result.restart_note.lower()
        or "auth" in result.restart_note.lower()
    )


def test_baseline_generates_intention_aware_restart_note_when_clean() -> None:
    """When clean, restart note connects intention to remaining criteria without empty claims."""
    packet = ReviewPacket(
        packet_id="pkt-clean-intent",
        timestamp_utc="2026-10-21T02:00:00Z",
        repo_name="sample-project",
        session_intention="Verify dark theme contrast and update tokens",
        acceptance_criteria=["Tokens meet WCAG AA"],
        changed_files=[
            ChangedFile(
                path="lib/theme.dart", diff="@@ -1,2 +1,2 @@\n+const dark = 0x001a06;\n"
            )
        ],
        check_receipts=[
            CheckReceipt(
                receipt_id="rcpt-contrast",
                command="flutter test test/theme_test.dart",
                exit_code=0,
                output_summary="1 passed",
                timestamp_utc="2026-10-21T02:00:00Z",
            )
        ],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    assert result.status == "clean"
    assert (
        "dark theme contrast" in result.restart_note.lower()
        or "tokens" in result.restart_note.lower()
    )
    assert "lib/theme.dart" in result.restart_note


def test_baseline_groups_missing_receipts_deterministically() -> None:
    """Baseline must group multiple missing check receipts into a single calm notice with scope details."""
    packet = ReviewPacket(
        packet_id="pkt-group-receipts",
        timestamp_utc="2026-10-25T01:00:00Z",
        repo_name="sample-project",
        session_intention="Add payment and checkout routes",
        acceptance_criteria=["Payment endpoint works", "Checkout UI updated"],
        changed_files=[
            ChangedFile(
                path="src/payment.py", diff="@@ -1,2 +1,2 @@\n+def pay(): pass\n"
            ),
            ChangedFile(
                path="src/checkout.py",
                diff="@@ -1,2 +1,2 @@\n+def checkout(): pass\n",
            ),
            ChangedFile(
                path="lib/views/checkout_view.dart",
                diff="@@ -1,2 +1,2 @@\n+class CheckoutView extends StatelessWidget {}\n",
            ),
        ],
        check_receipts=[],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    assert result.status == "findings_detected"

    unverified_receipt_findings = [
        f
        for f in result.findings
        if f.category == FindingCategory.UNVERIFIED
        and "receipt" in f.description.lower()
    ]
    # Exactly one consolidated notice for missing receipts
    assert len(unverified_receipt_findings) == 1
    grouped = unverified_receipt_findings[0]
    assert "tests were never run" not in grouped.description.lower()
    assert "failed to test" not in grouped.description.lower()
    assert "src/payment.py" in grouped.evidence
    assert "src/checkout.py" in grouped.evidence
    assert "lib/views/checkout_view.dart" in grouped.evidence


def test_baseline_non_layout_reconciliation_rejects_unrelated_receipt() -> None:
    """An unrelated passing receipt (e.g. test_payment.py) must NOT retire an unverified finding on auth.py."""
    prior = Finding(
        finding_id="f-auth-unverified",
        category=FindingCategory.UNVERIFIED,
        locator="src/auth.py:25",
        description="No check recorded for modified code.",
        status=FindingStatus.OPEN,
    )
    packet = ReviewPacket(
        packet_id="pkt-unrelated-scope",
        timestamp_utc="2026-10-25T01:00:00Z",
        repo_name="sample-project",
        session_intention="Refactor payment logic",
        acceptance_criteria=["Payment tests pass"],
        changed_files=[
            ChangedFile(
                path="src/payment.py", diff="@@ -1,2 +1,2 @@\n+def pay(): pass\n"
            )
        ],
        check_receipts=[
            CheckReceipt(
                receipt_id="rcpt-payment",
                command="pytest tests/test_payment.py",
                exit_code=0,
                output_summary="1 passed in 0.05s",
                timestamp_utc="2026-10-25T01:00:00Z",
            )
        ],
        prior_findings=[prior],
    )
    baseline = ChecklistBaseline()
    result = baseline.evaluate(packet)
    # The payment test receipt must NOT retire the auth finding!
    assert "f-auth-unverified" not in result.retired_finding_ids
