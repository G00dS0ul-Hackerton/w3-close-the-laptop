"""Core data models and schemas for SteadyDev review packets and results."""

from __future__ import annotations

import hashlib
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


def compute_finding_id(
    category: str | FindingCategory, locator: str, anchor: str = ""
) -> str:
    """Generate a deterministic, content-addressed finding identifier."""
    cat_val = category.value if hasattr(category, "value") else str(category)
    norm_loc = locator.strip().replace("\\", "/").lower()
    norm_anchor = anchor.strip().lower()[:40]
    raw = f"{cat_val}:{norm_loc}:{norm_anchor}".encode()
    digest = hashlib.sha256(raw).hexdigest()[:10]
    return f"fnd-{digest}"


class FindingCategory(str, Enum):
    EVIDENCE_MISMATCH = "evidence_mismatch"
    UNVERIFIED = "unverified"
    NEEDS_JUDGMENT = "needs_judgment"
    DEFERRED = "deferred"
    RECONCILED = "reconciled"

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            normalized = value.lower().replace("-", "_").replace(" ", "_")
            for member in cls:
                if member.value == normalized or normalized in member.value:
                    return member
                if "mismatch" in normalized:
                    return cls.EVIDENCE_MISMATCH
                if "unverified" in normalized:
                    return cls.UNVERIFIED
                if "judgment" in normalized:
                    return cls.NEEDS_JUDGMENT
                if "defer" in normalized:
                    return cls.DEFERRED
                if "reconcil" in normalized or "retire" in normalized:
                    return cls.RECONCILED
        return None


class FindingStatus(str, Enum):
    OPEN = "open"
    DEFERRED = "deferred"
    DISMISSED = "dismissed"
    USER_REPORTED_RESOLVED = "user-reported-resolved"
    EVIDENCE_RETIRED = "evidence-retired"

    @classmethod
    def _missing_(cls, value: object) -> Any:
        if isinstance(value, str):
            val_norm = value.lower().replace("_", "-")
            if "resolve" in val_norm:
                return cls.USER_REPORTED_RESOLVED
            if "retire" in val_norm:
                return cls.EVIDENCE_RETIRED
            for member in cls:
                if member.value == val_norm or member.name.lower() == val_norm:
                    return member
        return cls.OPEN


class CheckReceipt(BaseModel):
    receipt_id: str = Field(..., description="Unique receipt identifier")
    command: str = Field(..., description="Executed command string")
    exit_code: int = Field(..., description="Process exit code (0 = success)")
    output_summary: str = Field(..., description="Truncated stdout/stderr summary")
    timestamp_utc: str = Field(..., description="ISO 8601 UTC timestamp")


class Finding(BaseModel):
    finding_id: str = Field(default="", description="Unique finding ID")
    category: FindingCategory = Field(
        default=FindingCategory.EVIDENCE_MISMATCH, description="Finding category"
    )
    locator: str = Field(
        ..., description="Relative file path and optional line: file:line"
    )
    description: str = Field(..., description="Detailed explanation of the observation")
    evidence: str = Field(default="", description="Supporting factual evidence quote")
    status: FindingStatus = Field(
        default=FindingStatus.OPEN, description="Lifecycle status"
    )
    engine: str = Field(
        default="baseline-checklist",
        description="Engine that emitted this finding (e.g. gemma3:4b, qwen2.5-coder:3b, baseline-checklist)",
    )
    validation_error: str | None = Field(
        default=None, description="Locator validation failure reason if any"
    )
    is_stale: bool = Field(
        default=False, description="True if cited file no longer exists on disk"
    )
    stale_reason: str | None = Field(
        default=None, description="Reason if finding is marked stale"
    )
    user_reason: str | None = Field(
        default=None, description="User justification for lifecycle decision"
    )
    retired_by_receipt_id: str | None = Field(
        default=None, description="Receipt ID that retired this finding"
    )

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: Any) -> Any:
        if isinstance(v, str):
            res = FindingCategory._missing_(v)
            if res:
                return res
        return v

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(cls, v: Any) -> Any:
        if isinstance(v, str):
            res = FindingStatus._missing_(v)
            if res:
                return res
        return v


class ChangedFile(BaseModel):
    path: str = Field(..., description="Relative repository file path")
    status: str = Field(
        default="modified", description="Git status: modified, added, deleted"
    )
    diff: str = Field(default="", description="Unified diff hunk for this file")


class ReviewPacket(BaseModel):
    packet_id: str = Field(..., description="Unique packet identifier")
    timestamp_utc: str = Field(..., description="ISO 8601 UTC timestamp")
    repo_name: str = Field(..., description="Sanitized repository basename")
    session_intention: str = Field(..., description="High-level goal for the session")
    acceptance_criteria: list[str] = Field(
        default_factory=list, description="Numbered acceptance criteria"
    )
    changed_files: list[ChangedFile] = Field(
        default_factory=list, description="Allowlisted modified files and diffs"
    )
    check_receipts: list[CheckReceipt] = Field(
        default_factory=list, description="Verification receipts"
    )
    prior_findings: list[Finding] = Field(
        default_factory=list, description="Unresolved findings from previous reviews"
    )
    explicit_deferrals: list[str] = Field(
        default_factory=list, description="Explicitly deferred tasks for this session"
    )
    truncated: bool = Field(
        default=False, description="True if diff was truncated to protect context/CPU"
    )
    omitted_files: list[str] = Field(
        default_factory=list, description="Files excluded due to file count limits"
    )
    snapshot_hash: str | None = Field(
        default=None, description="Deterministic composite working-tree snapshot hash"
    )
    git_head_sha: str | None = Field(
        default=None, description="Current commit hash of Git HEAD"
    )


class ModelAttempt(BaseModel):
    model: str = Field(..., description="Model name attempted")
    outcome: str = Field(
        ...,
        description="success, timeout, schema_invalid, connection_error, cancelled",
    )
    duration_ms: float = Field(
        default=0.0, description="Duration of this attempt in milliseconds"
    )
    input_tokens: int | None = Field(
        default=None, description="Prompt tokens if captured"
    )
    output_tokens: int | None = Field(
        default=None, description="Generated tokens if captured"
    )
    done_reason: str | None = Field(
        default=None, description="Ollama done_reason, e.g. stop or length"
    )
    error_detail: str | None = Field(
        default=None, description="Sanitized error description"
    )


class ChunkProvenance(BaseModel):
    chunk_index: int = Field(..., description="1-based chunk index")
    total_chunks: int = Field(..., description="Total chunks in this review")
    file_paths: list[str] = Field(
        default_factory=list, description="Files included in this chunk"
    )
    attempts: list[ModelAttempt] = Field(
        default_factory=list, description="Model attempts for this chunk"
    )
    resolved_engine: str = Field(
        ..., description="Engine that provided final findings for this chunk"
    )
    fallback_reason: str | None = Field(
        default=None, description="Why chunk fell back (e.g. timeout_fallback)"
    )
    findings_count: int = Field(
        default=0, description="Number of findings produced by this chunk"
    )


class ReviewResult(BaseModel):
    packet_id: str = Field(..., description="Associated packet identifier")
    status: str = Field(
        ..., description="clean, findings_detected, unavailable, parse_error"
    )
    model_name: str | None = Field(
        default=None, description="Name of the model used (or None if baseline)"
    )
    model_digest: str | None = Field(
        default=None, description="Exact model blob digest if executed"
    )
    findings: list[Finding] = Field(
        default_factory=list, description="Active findings identified"
    )
    retired_finding_ids: list[str] = Field(
        default_factory=list,
        description="IDs of prior findings retired by new evidence",
    )
    closing_summary: str = Field(
        default="", description="Editable closing summary of session state"
    )
    restart_note: str = Field(
        default="", description="Durable next step recommendation for tomorrow"
    )
    timing_ms: dict[str, float] = Field(
        default_factory=dict, description="Execution timing breakdown in milliseconds"
    )
    raw_content: str = Field(
        default="", description="Exact raw text response emitted by LLM"
    )
    raw_json: dict[str, Any] | None = Field(
        default=None, description="Parsed raw JSON dictionary before post-processing"
    )
    chunk_provenance: list[ChunkProvenance] = Field(
        default_factory=list,
        description="Per-chunk model attempt and resolution provenance",
    )
    error: str | None = Field(
        default=None, description="Error message if review failed or fell back"
    )


class ReviewLifecycleRecord(BaseModel):
    """Real-time and historical review diagnostics for local UI."""

    review_id: str = Field(..., description="Unique review run identifier")
    phase: str = Field(
        default="idle",
        description="idle, starting, fingerprinting, auditing, synthesizing, completed, cancelled, timed_out, stale_snapshot",
    )
    is_reviewing: bool = Field(
        default=False, description="True while actively executing"
    )
    repo_name: str = Field(default="", description="Sanitized repository name")
    snapshot_hash: str | None = Field(default=None, description="Composite fingerprint")
    total_files: int = Field(default=0, description="Total changed files count")
    total_chunks: int = Field(default=0, description="Total chunks in this review")
    current_chunk: int = Field(default=0, description="Active chunk index")
    current_files: list[str] = Field(
        default_factory=list, description="Files in active chunk"
    )
    chunk_diagnostics: list[ChunkProvenance] = Field(
        default_factory=list,
        description="Per-chunk attempt history and provenance",
    )
    elapsed_ms: float = Field(
        default=0.0, description="Elapsed wall clock milliseconds"
    )
    deadline_seconds: float | None = Field(
        default=180.0,
        description="Workflow timeout deadline in seconds, or None for unlimited",
    )
    deadline_exceeded: bool = Field(
        default=False, description="Whether deadline was hit"
    )
    status: str = Field(default="idle", description="Final review status if completed")
    error: str | None = Field(default=None, description="Clean error summary if failed")
    created_at: str = Field(default="", description="ISO timestamp UTC")
    updated_at: str = Field(default="", description="ISO timestamp UTC")
