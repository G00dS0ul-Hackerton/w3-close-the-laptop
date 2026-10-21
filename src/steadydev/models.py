"""Core data models and schemas for SteadyDev review packets and results."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


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


class CheckReceipt(BaseModel):
    receipt_id: str = Field(..., description="Unique receipt identifier")
    command: str = Field(..., description="Executed command string")
    exit_code: int = Field(..., description="Process exit code (0 = success)")
    output_summary: str = Field(..., description="Truncated stdout/stderr summary")
    timestamp_utc: str = Field(..., description="ISO 8601 UTC timestamp")


class Finding(BaseModel):
    finding_id: str = Field(default="", description="Unique finding ID")
    category: FindingCategory = Field(..., description="Finding category")
    locator: str = Field(
        ..., description="Relative file path and optional line: file:line"
    )
    description: str = Field(..., description="Detailed explanation of the observation")
    evidence: str = Field(default="", description="Supporting factual evidence quote")
    status: FindingStatus = Field(
        default=FindingStatus.OPEN, description="Lifecycle status"
    )
    validation_error: str | None = Field(
        default=None, description="Locator validation failure reason if any"
    )

    @field_validator("category", mode="before")
    @classmethod
    def normalize_category(cls, v: Any) -> Any:
        if isinstance(v, str):
            res = FindingCategory._missing_(v)
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
    error: str | None = Field(
        default=None, description="Error message if review failed or fell back"
    )
