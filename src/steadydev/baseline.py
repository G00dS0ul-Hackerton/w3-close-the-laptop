"""Deterministic non-AI checklist baseline engine.

Evaluates session context using structural heuristics and receipt presence rules.
Deterministic rules; no LLM inference. Rules can still produce false positives and false negatives.
"""

import re
import time

from steadydev.models import (
    Finding,
    FindingCategory,
    FindingStatus,
    ReviewPacket,
    ReviewResult,
)

LAYOUT_EXTENSIONS = {".html", ".css", ".scss", ".jsx", ".tsx", ".vue"}
CODE_EXTENSIONS = {".py", ".dart", ".ts", ".js", ".go", ".rs", ".java", ".c", ".cpp"}
LAYOUT_TERMS = {"viewport", "screenshot", "widget", "ui", "browser"}
UI_DIRS = {"widgets/", "views/", "pages/", "screens/", "ui/", "components/"}
UI_DIFF_TOKENS = {
    "widget",
    "build(",
    "statefulwidget",
    "statelesswidget",
    "layoutbuilder",
    "row(",
    "column(",
    "container(",
}


def _is_layout_file(file_path: str, diff_text: str) -> bool:
    """Determine whether a file is a UI/layout file requiring viewport checks."""
    path_lower = file_path.lower()
    ext = path_lower[path_lower.rfind(".") :] if "." in path_lower else ""
    if ext in LAYOUT_EXTENSIONS:
        return True
    if ext == ".dart":
        # Check if located in a designated UI directory
        if any(d in path_lower for d in UI_DIRS):
            return True
        # Check if diff includes UI widget construction or layout keywords
        diff_lower = diff_text.lower()
        return any(token in diff_lower for token in UI_DIFF_TOKENS)
    return False


def _is_criterion_deferred(criterion: str, deferrals: list[str]) -> bool:
    """Check if a specific criterion was explicitly deferred with meaningful keyword overlap."""
    crit_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", criterion.lower()))
    for d in deferrals:
        d_lower = d.lower()
        if len(d_lower) >= 4 and (
            d_lower in criterion.lower() or criterion.lower() in d_lower
        ):
            return True
        d_words = set(re.findall(r"\b[a-zA-Z]{4,}\b", d_lower))
        if len(crit_words.intersection(d_words)) >= 2:
            return True
    return False


class ChecklistBaseline:
    """Deterministic, rule-based review baseline."""

    def evaluate(self, packet: ReviewPacket) -> ReviewResult:
        start_time = time.perf_counter()

        findings: list[Finding] = []
        retired_finding_ids: list[str] = []

        changed_paths = [f.path for f in packet.changed_files]
        changed_extensions = {
            f.path[f.path.rfind(".") :].lower()
            for f in packet.changed_files
            if "." in f.path
        }

        # 0. Check for failed receipts
        for r in packet.check_receipts:
            if r.exit_code != 0:
                findings.append(
                    Finding(
                        finding_id=f"base-f-{len(findings) + 1}",
                        category=FindingCategory.UNVERIFIED,
                        locator=changed_paths[0] if changed_paths else "repo:1",
                        description=f"Check execution failed with exit code {r.exit_code}: {r.command}",
                        evidence=r.output_summary
                        or f"Command '{r.command}' exited with code {r.exit_code}",
                        status=FindingStatus.OPEN,
                    )
                )

        passing_receipts = [r for r in packet.check_receipts if r.exit_code == 0]
        passing_commands = " ".join(r.command.lower() for r in passing_receipts)

        # 1. Reconcile prior findings with relevant passing receipts
        for pf in packet.prior_findings:
            if (
                pf.category == FindingCategory.UNVERIFIED
                and pf.status == FindingStatus.OPEN
            ):
                desc_lower = (pf.description + " " + pf.locator).lower()
                is_layout_finding = any(
                    term in desc_lower for term in ["layout", "viewport", "widget"]
                )

                if is_layout_finding:
                    # Layout finding requires a relevant viewport/widget passing check
                    has_relevant_pass = any(
                        term in passing_commands for term in LAYOUT_TERMS
                    )
                else:
                    has_relevant_pass = bool(passing_receipts)

                if has_relevant_pass:
                    retired_finding_ids.append(pf.finding_id)

        # 2. Check layout modifications for viewport/widget receipts
        layout_files = [
            f for f in packet.changed_files if _is_layout_file(f.path, f.diff)
        ]
        has_layout_changes = bool(layout_files)
        has_viewport_receipt = any(term in passing_commands for term in LAYOUT_TERMS)

        if has_layout_changes and not has_viewport_receipt:
            # Check if layout specifically deferred
            is_deferred = any(
                "layout" in d.lower() or "viewport" in d.lower()
                for d in packet.explicit_deferrals
            )
            if not is_deferred:
                layout_file = layout_files[0].path if layout_files else "layout"
                findings.append(
                    Finding(
                        finding_id=f"base-f-{len(findings) + 1}",
                        category=FindingCategory.UNVERIFIED,
                        locator=f"{layout_file}:1",
                        description="No check recorded for modified layout.",
                        evidence="Layout files modified without an attached passing viewport, widget, or screenshot test receipt.",
                        status=FindingStatus.OPEN,
                    )
                )

        # 3. Check code modifications for test receipts
        has_code_changes = bool(changed_extensions.intersection(CODE_EXTENSIONS))
        if has_code_changes and not passing_receipts:
            findings.append(
                Finding(
                    finding_id=f"base-f-{len(findings) + 1}",
                    category=FindingCategory.UNVERIFIED,
                    locator=changed_paths[0] if changed_paths else "repo:1",
                    description="No passing check recorded for modified code.",
                    evidence="Source code modified with zero attached passing check receipts.",
                    status=FindingStatus.OPEN,
                )
            )

        # 4. Check criteria keywords against modified files
        for criterion in packet.acceptance_criteria:
            if _is_criterion_deferred(criterion, packet.explicit_deferrals):
                continue

            crit_lower = criterion.lower()
            # If criterion specifically demands README / documentation
            if (
                "readme" in crit_lower
                or "documentation" in crit_lower
                or "docs" in crit_lower
            ):
                doc_touched = any(
                    "readme" in p.lower() or p.startswith("docs/")
                    for p in changed_paths
                )
                if not doc_touched:
                    findings.append(
                        Finding(
                            finding_id=f"base-f-{len(findings) + 1}",
                            category=FindingCategory.UNVERIFIED,
                            locator="README.md:1",
                            description=f"Documentation criterion not verified: {criterion}",
                            evidence=f"Criterion '{criterion}' specified but no documentation files modified.",
                            status=FindingStatus.OPEN,
                        )
                    )

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0

        status = "findings_detected" if findings else "clean"
        closing_summary = (
            f"Baseline Checklist Review: {len(packet.changed_files)} files modified, "
            f"{len(packet.check_receipts)} checks recorded, {len(findings)} unverified gaps."
        )
        restart_note = (
            "Continue by addressing open unverified checks."
            if findings
            else "No gaps detected by the baseline's limited rules; this does not establish that all requirements were verified."
        )

        return ReviewResult(
            packet_id=packet.packet_id,
            status=status,
            model_name="baseline-checklist",
            findings=findings,
            retired_finding_ids=retired_finding_ids,
            closing_summary=closing_summary,
            restart_note=restart_note,
            timing_ms={
                "total_duration_ms": elapsed_ms,
                "eval_duration_ms": elapsed_ms,
            },
        )
