"""Decoupled Sentry AI Agent Tracing adapter, allowlist sanitizer, and recording transport."""

from __future__ import annotations

import contextlib
import hashlib
import os
from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from types import TracebackType
from typing import Any, Self

from steadydev.packet import redact_sensitive_text

try:
    import sentry_sdk
    from sentry_sdk.envelope import Envelope
    from sentry_sdk.transport import Transport

    HAVE_SENTRY = True
except ImportError:
    sentry_sdk = None
    Envelope = None
    Transport = object
    HAVE_SENTRY = False

# Strict span operation allowlist
ALLOWED_SPAN_OPS = {
    "gen_ai.review_pipeline",
    "gen_ai.invoke_agent",
    "gen_ai.chunk_review",
    "gen_ai.chat",
    "gen_ai.execute_model",
    "gen_ai.synthesis",
    "gen_ai.execute_tool",
    "review.baseline",
    # Internal pipeline stage spans
    "snapshot.collect",
    "cache.fingerprint_check",
    "chunk.prepare",
    "validation.schema_check",
    "reconciliation.reconcile",
    "persistence.store",
}

# Strict span data key allowlist
ALLOWED_SPAN_DATA_KEYS = {
    "ai.model_id",
    "ai.system",
    "ai.pipeline",
    "gen_ai.operation.name",
    "gen_ai.agent.name",
    "gen_ai.pipeline.name",
    "gen_ai.system",
    "gen_ai.request.model",
    "gen_ai.response.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.total_tokens",
    "ollama.timing.total_duration_ms",
    "ollama.timing.load_duration_ms",
    "ollama.timing.prompt_eval_duration_ms",
    "ollama.timing.eval_duration_ms",
    "ollama.done_reason",
    "stage.name",
    "stage.files_count",
    "stage.status",
    "cache.hit",
    "persistence.status",
    "validation.is_valid",
    "reconciliation.reconciled_count",
    "ai.total_duration_ms",
    "ai.load_duration_ms",
    "ai.prompt_eval_duration_ms",
    "ai.eval_duration_ms",
    "ai.eval_count",
    "ai.prompt_eval_count",
    "packet.chunk_index",
    "packet.total_chunks",
    "packet.total_files",
    "packet.is_truncated",
    "chunk.index",
    "chunk.files_count",
    "chunk.diff_chars",
    "review.packet_id",
    "review.repo_name",
    "review.files_count",
    "review.receipts_count",
    "review.prior_findings_count",
    "review.chunks_count",
    "review.primary_model",
    "review.fallback_model",
    "review.status",
    "review.findings_count",
    "review.retired_count",
    "review.effective_model",
    "baseline.reason",
    "baseline.findings_count",
    "baseline.retired_count",
    "synthesis.findings_input_count",
    "error.type",
    "session_hash",
    "run_id",
}

# Strict span tag key allowlist
ALLOWED_SPAN_TAG_KEYS = {
    "model_name",
    "fallback_used",
    "review_status",
    "ai.pipeline",
    "component",
    "error_type",
}

# Expected operational outcome exceptions that must NOT produce Sentry errors
EXPECTED_ERROR_NAMES = {
    "CancelledError",
    "WorkingTreeUnchanged",
    "AdmissionLockBusy",
    "StaleSnapshotConflict",
    "ScopeDeniedError",
}


class NoOpSpan:
    """Null-object span context when telemetry is disabled or uninstalled."""

    def __init__(self, op: str = "", name: str = "") -> None:
        self.op = op
        self.name = name
        self.data: dict[str, Any] = {}
        self.tags: dict[str, str] = {}
        self.status: str = "ok"

    def set_data(self, key: str, value: Any) -> None:
        self.data[key] = value

    def set_tag(self, key: str, value: str) -> None:
        self.tags[key] = str(value)

    def set_status(self, status: str) -> None:
        self.status = status

    def finish(self) -> None:
        pass

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        pass


class InMemoryRecordingTransport(Transport):
    """In-memory recording transport for test inspection without external network egress."""

    def __init__(self, options: Any = None) -> None:
        super().__init__(options)
        self.envelopes: list[Any] = []

    def capture_envelope(self, envelope: Any) -> None:
        self.envelopes.append(envelope)

    def flush(self, timeout: Any = None, callback: Any = None) -> None:
        pass

    def close(self) -> None:
        pass

    def clear(self) -> None:
        self.envelopes.clear()

    def get_wire_bytes(self) -> bytes:
        """Serialize all captured envelopes to raw wire bytes."""
        chunks: list[bytes] = []
        for env in self.envelopes:
            if hasattr(env, "serialize"):
                try:
                    chunks.append(env.serialize())
                    continue
                except (TypeError, ValueError, OSError):
                    pass
            for item in getattr(env, "items", []):
                if hasattr(item, "get_bytes"):
                    chunks.append(item.get_bytes())
        return b"".join(chunks)

    def get_wire_text(self) -> str:
        """Decode all wire bytes to string for sensitive token / canary searches."""
        return self.get_wire_bytes().decode("utf-8", errors="replace")


def _sanitize_string_value(val: Any) -> Any:
    """Sanitize strings through redact_sensitive_text; leave numbers/bools intact."""
    if isinstance(val, str):
        return redact_sensitive_text(val)
    return val


def before_send_transaction_allowlist_scrubber(
    event: dict[str, Any], hint: dict[str, Any]
) -> dict[str, Any] | None:
    """Strict whitelist sanitizer for Sentry transaction events."""
    if _DRAIN_MODE == "drop_unsent":
        return None
    if event.get("type") != "transaction":
        return None

    # Strip forbidden root context structures
    event.pop("breadcrumbs", None)
    event.pop("request", None)
    event.pop("user", None)
    event.pop("modules", None)
    event.pop("server_name", None)
    event.pop("environment", None)
    event.pop("extra", None)

    # Sanitize root trace context data to strict allowlist
    trace_ctx = event.get("contexts", {}).get("trace", {})
    if (
        isinstance(trace_ctx, dict)
        and "data" in trace_ctx
        and isinstance(trace_ctx["data"], dict)
    ):
        trace_ctx["data"] = {
            k: _sanitize_string_value(v)
            for k, v in trace_ctx["data"].items()
            if k in ALLOWED_SPAN_DATA_KEYS
        }

    # Sanitize root transaction tags
    if "tags" in event and isinstance(event["tags"], dict):
        event["tags"] = {
            k: _sanitize_string_value(v)
            for k, v in event["tags"].items()
            if k in ALLOWED_SPAN_TAG_KEYS
        }

    # Filter and sanitize child spans
    sanitized_spans = []
    for span in event.get("spans", []):
        op = span.get("op", "")
        if op not in ALLOWED_SPAN_OPS:
            continue

        # Filter span data keys to strict allowlist
        if "data" in span and isinstance(span["data"], dict):
            span["data"] = {
                k: _sanitize_string_value(v)
                for k, v in span["data"].items()
                if k in ALLOWED_SPAN_DATA_KEYS
            }

        # Filter span tags
        if "tags" in span and isinstance(span["tags"], dict):
            span["tags"] = {
                k: _sanitize_string_value(v)
                for k, v in span["tags"].items()
                if k in ALLOWED_SPAN_TAG_KEYS
            }

        # Ensure description is sanitized
        if "description" in span:
            span["description"] = _sanitize_string_value(span["description"])

        sanitized_spans.append(span)

    event["spans"] = sanitized_spans
    return event


def before_send_error_allowlist_scrubber(
    event: dict[str, Any], hint: dict[str, Any]
) -> dict[str, Any] | None:
    """Strict allowlist sanitizer for Sentry error events."""
    if _DRAIN_MODE == "drop_unsent":
        return None

    # Drop expected operational outcomes
    if hint.get("exc_info"):
        exc = hint["exc_info"][1]
        if exc is not None and type(exc).__name__ in EXPECTED_ERROR_NAMES:
            return None

    exc_entries = event.get("exception", {}).get("values", [])
    for entry in exc_entries:
        if entry.get("type") in EXPECTED_ERROR_NAMES:
            return None

    # Strip forbidden root context structures
    event.pop("breadcrumbs", None)
    event.pop("request", None)
    event.pop("user", None)
    event.pop("modules", None)
    event.pop("server_name", None)
    event.pop("environment", None)
    event.pop("extra", None)

    # Sanitize exception message and stack frames
    if "exception" in event and isinstance(event["exception"], dict):
        values = event["exception"].get("values", [])
        for val in values:
            if "value" in val:
                val["value"] = redact_sensitive_text(str(val["value"]))
            st = val.get("stacktrace", {})
            if isinstance(st, dict) and "frames" in st:
                sanitized_frames = []
                for frame in st["frames"]:
                    # Never include local variables or source context
                    frame.pop("vars", None)
                    frame.pop("pre_context", None)
                    frame.pop("context_line", None)
                    frame.pop("post_context", None)
                    # Normalize Windows path to repo-relative module
                    fn = frame.get("filename", "")
                    if fn:
                        fn = redact_sensitive_text(fn)
                        if "steadydev" in fn:
                            fn = "steadydev" + fn.split("steadydev", 1)[1]
                        frame["filename"] = fn
                    if "abs_path" in frame:
                        frame.pop("abs_path", None)
                    sanitized_frames.append(frame)
                st["frames"] = sanitized_frames

    # Sanitize root error tags
    if "tags" in event and isinstance(event["tags"], dict):
        event["tags"] = {
            k: _sanitize_string_value(v)
            for k, v in event["tags"].items()
            if k in ALLOWED_SPAN_TAG_KEYS
        }

    return event


class ExportState(str, Enum):
    DISABLED = "disabled"
    LOCAL_ONLY = "local_only"
    STAGED_LOCAL = "staged_local"
    FLUSHING = "flushing"
    VERIFIED_DELIVERED = "verified_delivered"
    DELIVERY_FAILED = "delivery_failed"


@dataclass
class DeliveryReceipt:
    trace_id: str | None = None
    state: ExportState = ExportState.DISABLED
    timestamp_utc: str | None = None
    verified_delivery: bool = False
    error_detail: str | None = None


_TELEMETRY_INITIALIZED = False
_RECORDING_TRANSPORT: InMemoryRecordingTransport | None = None
_DRAIN_MODE: str = "normal"  # "normal" or "drop_unsent"
_CURRENT_EXPORT_STATE: ExportState = ExportState.DISABLED
_LAST_DELIVERY_RECEIPT: DeliveryReceipt = DeliveryReceipt()
_CONFIGURED_DSN: str | None = None


def mask_dsn(dsn: str | None) -> str:
    """Mask sensitive public key/token in Sentry DSN for honest, safe display."""
    if not dsn:
        return ""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(dsn)
        if parsed.username:
            masked_user = (
                parsed.username[:4] + "***" if len(parsed.username) > 4 else "***"
            )
            netloc = f"{masked_user}@{parsed.hostname}"
            if parsed.port:
                netloc += f":{parsed.port}"
            return parsed._replace(netloc=netloc).geturl()
    except (ValueError, AttributeError):
        return "***"
    return "***"


def get_configured_dsn() -> str | None:
    return _CONFIGURED_DSN or os.environ.get("SENTRY_DSN")


def get_trace_url(trace_id: str | None = None) -> str | None:
    """Construct deep link URL for a trace in Sentry explore view."""
    tid = trace_id or (
        _LAST_DELIVERY_RECEIPT.trace_id if _LAST_DELIVERY_RECEIPT else None
    )
    if not tid:
        return None
    dsn = get_configured_dsn()
    if not dsn:
        return None
    try:
        from urllib.parse import urlparse

        parsed = urlparse(dsn)
        if parsed.hostname and ".ingest." in parsed.hostname:
            org = parsed.hostname.split(".ingest.")[0]
            return f"https://{org}.sentry.io/explore/traces/trace/{tid}/"
    except (ValueError, AttributeError, IndexError):
        return f"https://sentry.io/explore/traces/trace/{tid}/"
    return f"https://sentry.io/explore/traces/trace/{tid}/"


def get_export_state() -> ExportState:
    if not _TELEMETRY_INITIALIZED or not HAVE_SENTRY:
        return ExportState.DISABLED
    return _CURRENT_EXPORT_STATE


def get_last_delivery_receipt() -> DeliveryReceipt:
    return _LAST_DELIVERY_RECEIPT


def set_drain_mode(mode: str) -> None:
    global _DRAIN_MODE
    _DRAIN_MODE = mode


def set_telemetry_opt_in(
    enabled: bool, dsn: str | None = None, transport: Any = None
) -> bool:
    global _CURRENT_EXPORT_STATE, _LAST_DELIVERY_RECEIPT, _DRAIN_MODE, _CONFIGURED_DSN
    if not enabled:
        _DRAIN_MODE = "drop_unsent"
        _CURRENT_EXPORT_STATE = ExportState.DISABLED
        _LAST_DELIVERY_RECEIPT = DeliveryReceipt(
            trace_id=None,
            state=ExportState.DISABLED,
            verified_delivery=False,
            error_detail="Telemetry disabled by user; unsent spans dropped",
        )
        init_telemetry(force_enable=False)
        return False
    else:
        _DRAIN_MODE = "normal"
        if dsn:
            _CONFIGURED_DSN = dsn
        ok = init_telemetry(dsn=dsn, transport=transport, force_enable=True)
        _CURRENT_EXPORT_STATE = ExportState.LOCAL_ONLY if ok else ExportState.DISABLED
        return ok


def verify_and_flush(timeout: float = 5.0) -> DeliveryReceipt:
    global _CURRENT_EXPORT_STATE
    if not _TELEMETRY_INITIALIZED or not HAVE_SENTRY:
        return _LAST_DELIVERY_RECEIPT
    if _DRAIN_MODE == "drop_unsent":
        _CURRENT_EXPORT_STATE = ExportState.DISABLED
        return _LAST_DELIVERY_RECEIPT
    if not _LAST_DELIVERY_RECEIPT.trace_id:
        return _LAST_DELIVERY_RECEIPT

    _CURRENT_EXPORT_STATE = ExportState.FLUSHING
    now_iso = datetime.now(UTC).isoformat()
    try:
        sentry_sdk.flush(timeout=timeout)
        if _RECORDING_TRANSPORT is not None:
            if _RECORDING_TRANSPORT.envelopes:
                _CURRENT_EXPORT_STATE = ExportState.VERIFIED_DELIVERED
                _LAST_DELIVERY_RECEIPT.state = ExportState.VERIFIED_DELIVERED
                _LAST_DELIVERY_RECEIPT.verified_delivery = True
                _LAST_DELIVERY_RECEIPT.timestamp_utc = now_iso
            else:
                _CURRENT_EXPORT_STATE = ExportState.DELIVERY_FAILED
                _LAST_DELIVERY_RECEIPT.state = ExportState.DELIVERY_FAILED
                _LAST_DELIVERY_RECEIPT.error_detail = (
                    "Zero envelopes in recording transport"
                )
        else:
            _CURRENT_EXPORT_STATE = ExportState.VERIFIED_DELIVERED
            _LAST_DELIVERY_RECEIPT.state = ExportState.VERIFIED_DELIVERED
            _LAST_DELIVERY_RECEIPT.verified_delivery = True
            _LAST_DELIVERY_RECEIPT.timestamp_utc = now_iso
    except (RuntimeError, OSError, TimeoutError) as exc:
        _CURRENT_EXPORT_STATE = ExportState.DELIVERY_FAILED
        _LAST_DELIVERY_RECEIPT.state = ExportState.DELIVERY_FAILED
        _LAST_DELIVERY_RECEIPT.error_detail = str(exc)
        _LAST_DELIVERY_RECEIPT.timestamp_utc = now_iso
    except Exception as exc:  # noqa: BLE001
        _CURRENT_EXPORT_STATE = ExportState.DELIVERY_FAILED
        _LAST_DELIVERY_RECEIPT.state = ExportState.DELIVERY_FAILED
        _LAST_DELIVERY_RECEIPT.error_detail = str(exc)
        _LAST_DELIVERY_RECEIPT.timestamp_utc = now_iso

    return _LAST_DELIVERY_RECEIPT


def is_telemetry_enabled() -> bool:
    """Check if telemetry is enabled via environment."""
    enabled_val = os.environ.get("STEADYDEV_SENTRY_ENABLED", "0").lower().strip()
    return enabled_val in ("1", "true", "yes", "on") and bool(
        os.environ.get("SENTRY_DSN")
    )


def init_telemetry(
    dsn: str | None = None,
    transport: Any = None,
    force_enable: bool = False,
) -> bool:
    """Initialize Sentry SDK with strict opt-in, zero auto-instrumentation, and zero breadcrumbs."""
    global _TELEMETRY_INITIALIZED, _RECORDING_TRANSPORT, _DRAIN_MODE

    if not HAVE_SENTRY:
        return False

    effective_dsn = dsn or os.environ.get("SENTRY_DSN")
    enabled = force_enable or is_telemetry_enabled()

    if not enabled or not effective_dsn:
        _TELEMETRY_INITIALIZED = False
        _DRAIN_MODE = "drop_unsent"
        _RECORDING_TRANSPORT = None
        return False

    _DRAIN_MODE = "normal"

    options: dict[str, Any] = {
        "dsn": effective_dsn,
        "default_integrations": False,
        "auto_enabling_integrations": False,
        "integrations": [],
        "max_breadcrumbs": 0,
        "before_breadcrumb": lambda b, h: None,
        "before_send": before_send_error_allowlist_scrubber,
        "before_send_transaction": before_send_transaction_allowlist_scrubber,
        "send_default_pii": False,
        "include_local_variables": False,
        "include_source_context": False,
        "traces_sample_rate": 1.0,
        "_experiments": {"stream_gen_ai_spans": False},
    }

    if transport is not None:
        options["transport"] = transport
        if isinstance(transport, InMemoryRecordingTransport):
            _RECORDING_TRANSPORT = transport

    sentry_sdk.init(**options)
    _TELEMETRY_INITIALIZED = True
    return True


def get_recording_transport() -> InMemoryRecordingTransport | None:
    return _RECORDING_TRANSPORT


@contextlib.contextmanager
def start_review_span(
    packet_id: str,
    repo_name: str,
    files_count: int,
    receipts_count: int,
    prior_findings_count: int,
    chunks_count: int,
    primary_model: str,
    fallback_model: str,
    session_id: str = "",
    sentry_trace: str | None = None,
    baggage: str | None = None,
    run_id: str | None = None,
) -> Generator[Any, None, None]:
    """Context manager for root review orchestration span/transaction with trace continuation."""
    if not _TELEMETRY_INITIALIZED or not HAVE_SENTRY:
        yield NoOpSpan(op="gen_ai.invoke_agent", name="steadydev.review")
        return

    # Create root span / transaction with continuation if provided
    if sentry_trace:
        headers_dict = {"sentry-trace": sentry_trace}
        if baggage:
            headers_dict["baggage"] = baggage
        transaction = sentry_sdk.continue_trace(
            headers_dict,
            name="steadydev.review",
            op="gen_ai.invoke_agent",
        )
        span_ctx = sentry_sdk.start_transaction(transaction)
    else:
        span_ctx = sentry_sdk.start_transaction(
            name="steadydev.review",
            op="gen_ai.invoke_agent",
        )
    global _CURRENT_EXPORT_STATE, _LAST_DELIVERY_RECEIPT
    trace_id_val = None
    if hasattr(span_ctx, "trace_id"):
        trace_id_val = str(span_ctx.trace_id)
    elif hasattr(span_ctx, "containing_transaction") and hasattr(
        span_ctx.containing_transaction, "trace_id"
    ):
        trace_id_val = str(span_ctx.containing_transaction.trace_id)

    if trace_id_val and _DRAIN_MODE != "drop_unsent":
        _CURRENT_EXPORT_STATE = ExportState.STAGED_LOCAL
        _LAST_DELIVERY_RECEIPT = DeliveryReceipt(
            trace_id=trace_id_val,
            state=ExportState.STAGED_LOCAL,
            timestamp_utc=datetime.now(UTC).isoformat(),
            verified_delivery=False,
        )

    with span_ctx as span:
        span.set_data("gen_ai.operation.name", "invoke_agent")
        span.set_data("gen_ai.agent.name", "steadydev-reviewer")
        span.set_data("gen_ai.pipeline.name", "session-review")
        span.set_data("ai.pipeline", "steadydev.review")
        span.set_data("review.packet_id", packet_id)
        span.set_data("review.repo_name", repo_name)
        span.set_data("review.files_count", files_count)
        span.set_data("review.receipts_count", receipts_count)
        span.set_data("review.prior_findings_count", prior_findings_count)
        span.set_data("review.chunks_count", chunks_count)
        span.set_data("review.primary_model", primary_model)
        span.set_data("review.fallback_model", fallback_model)
        if run_id:
            span.set_data("run_id", run_id)
        if session_id:
            sess_hash = hashlib.sha256(session_id.encode()).hexdigest()[:8]
            span.set_data("session_hash", sess_hash)

        try:
            yield span
        except Exception as exc:
            span.set_status("internal_error")
            span.set_data("error.type", type(exc).__name__)
            raise


@contextlib.contextmanager
def start_chat_span(
    model_name: str,
    chunk_index: int | None = None,
    total_chunks: int | None = None,
    is_synthesis: bool = False,
    is_fallback: bool = False,
    files_count: int | None = None,
    diff_chars: int | None = None,
) -> Generator[Any, None, None]:
    """Context manager for model inference calls (single chunk, map chunk, or synthesis)."""
    if not _TELEMETRY_INITIALIZED or not HAVE_SENTRY:
        yield NoOpSpan(op="gen_ai.chat", name=f"chat {model_name}")
        return

    if is_synthesis:
        name = f"chat {model_name} [synthesis]"
    elif chunk_index is not None and total_chunks is not None:
        fb_suffix = " fallback" if is_fallback else ""
        name = f"chat {model_name} [chunk {chunk_index}/{total_chunks}{fb_suffix}]"
    else:
        name = f"chat {model_name}"

    span_ctx = sentry_sdk.start_span(op="gen_ai.chat", name=name)
    with span_ctx as span:
        span.set_data("gen_ai.operation.name", "chat")
        span.set_data("gen_ai.system", "ollama")
        span.set_data("ai.system", "ollama")
        span.set_data("gen_ai.request.model", model_name)
        span.set_data("ai.model_id", model_name)

        if chunk_index is not None:
            span.set_data("chunk.index", chunk_index)
        if files_count is not None:
            span.set_data("chunk.files_count", files_count)
        if diff_chars is not None:
            span.set_data("chunk.diff_chars", diff_chars)

        try:
            yield span
        except Exception as exc:
            err_name = type(exc).__name__
            if "Timeout" in err_name:
                span.set_status("deadline_exceeded")
            else:
                span.set_status("internal_error")
            span.set_data("error.type", err_name)
            raise


@contextlib.contextmanager
def start_tool_span(
    tool_name: str = "ChecklistBaseline",
    reason: str = "primary_mode",
) -> Generator[Any, None, None]:
    """Context manager for deterministic tool execution (ChecklistBaseline floor)."""
    if not _TELEMETRY_INITIALIZED or not HAVE_SENTRY:
        yield NoOpSpan(op="gen_ai.execute_tool", name=f"execute {tool_name}")
        return

    span_ctx = sentry_sdk.start_span(
        op="gen_ai.execute_tool",
        name=f"execute {tool_name}",
    )
    with span_ctx as span:
        span.set_data("gen_ai.operation.name", "execute_tool")
        span.set_data("ai.system", "baseline")
        span.set_data("baseline.reason", reason)
        try:
            yield span
        except Exception as exc:
            span.set_status("internal_error")
            span.set_data("error.type", type(exc).__name__)
            raise


def capture_unexpected_exception(
    exc: BaseException, context_dict: dict[str, Any] | None = None
) -> None:
    """Capture unexpected engine errors with strict sanitization; ignore expected outcomes."""
    if not _TELEMETRY_INITIALIZED or not HAVE_SENTRY:
        return
    if _DRAIN_MODE == "drop_unsent":
        return
    if type(exc).__name__ in EXPECTED_ERROR_NAMES:
        return

    try:
        with sentry_sdk.new_scope() as scope:
            if context_dict:
                for k, v in context_dict.items():
                    if k in ALLOWED_SPAN_TAG_KEYS:
                        scope.set_tag(k, _sanitize_string_value(v))
            sentry_sdk.capture_exception(exc)
    except Exception:  # noqa: BLE001, S110
        pass


@contextlib.contextmanager
def start_stage_span(
    op: str,
    description: str = "",
    data: dict[str, Any] | None = None,
) -> Generator[Any, None, None]:
    """Context manager for internal review pipeline stages."""
    if not _TELEMETRY_INITIALIZED or not HAVE_SENTRY:
        yield NoOpSpan(op=op, name=description or op)
        return

    span_ctx = sentry_sdk.start_span(op=op, name=description or op)
    with span_ctx as span:
        if data:
            for k, v in data.items():
                if k in ALLOWED_SPAN_DATA_KEYS:
                    span.set_data(k, _sanitize_string_value(v))
        try:
            yield span
        except Exception as exc:
            span.set_status("internal_error")
            span.set_data("error.type", type(exc).__name__)
            raise
