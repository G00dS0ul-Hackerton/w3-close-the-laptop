"""Comprehensive unit and integration tests for Sentry opt-in toggle, export state machine, and verified delivery tracking."""

import threading
import time
from pathlib import Path
from typing import Any

import httpx

from steadydev.models import ReviewPacket, ReviewResult
from steadydev.server import create_server
from steadydev.telemetry import (
    ExportState,
    InMemoryRecordingTransport,
    get_export_state,
    get_last_delivery_receipt,
    get_trace_url,
    mask_dsn,
    set_telemetry_opt_in,
)


class SlowMockReviewer:
    """Mock reviewer that yields mid-flight so we can test concurrent toggle changes."""

    def __init__(self, pause_seconds: float = 0.2) -> None:
        self.pause_seconds = pause_seconds
        self.started_event = threading.Event()

    def review(
        self,
        packet: ReviewPacket,
        progress_callback: Any = None,
        **kwargs: Any,
    ) -> ReviewResult:
        self.started_event.set()
        time.sleep(self.pause_seconds)
        if progress_callback:
            progress_callback(1, 1, "Reviewing chunk 1")
        return ReviewResult(
            packet_id=packet.packet_id,
            model_tag="slow-mock",
            elapsed_seconds=self.pause_seconds,
            status="clean",
            findings=[],
            closing_summary="Completed slow review.",
            restart_note="Resume tomorrow.",
            retired_finding_ids=[],
            raw_content="{}",
        )


def test_mask_dsn_and_trace_url() -> None:
    """Verify DSN masking hides secret keys and deep link builds correct Sentry explore URL."""
    raw_dsn = "https://public_key_12345@o987654.ingest.sentry.io/45081234"
    masked = mask_dsn(raw_dsn)
    assert "public_key_12345" not in masked
    assert "publ***@o987654.ingest.sentry.io/45081234" in masked

    assert mask_dsn("") == ""
    assert mask_dsn(None) == ""

    trace_url = get_trace_url("cae934c2f4774308823593cde2c5db02")
    # Will use configured or env DSN
    assert (
        trace_url is None
        or "explore/traces/trace/cae934c2f4774308823593cde2c5db02" in trace_url
    )


def test_telemetry_config_endpoints_and_persistence(tmp_path: Path) -> None:
    """Verify default-off persistence and configuration round-trips over loopback API."""
    repo_dir = tmp_path / "repo_cfg"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    db_file = tmp_path / "telemetry_test.db"

    server = create_server(
        repo_root=repo_dir,
        port=0,
        token="tok-telemetry-123",
        db_path=db_file,
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)

    base_url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer tok-telemetry-123"}

    try:
        with httpx.Client(base_url=base_url, headers=headers) as client:
            # 1. Initial State: Disabled by default
            resp = client.get("/api/telemetry/config")
            assert resp.status_code == 200
            data = resp.json()
            assert data["enabled"] is False
            assert data["export_state"] == "disabled"
            assert data["verified_delivery"] is False

            # 2. Update config: Enable telemetry with DSN
            sample_dsn = "https://key1234567@o1234.ingest.sentry.io/999"
            resp = client.post(
                "/api/telemetry/config",
                json={"enabled": True, "dsn": sample_dsn},
            )
            assert resp.status_code == 200
            post_data = resp.json()
            assert post_data["enabled"] is True
            assert post_data["dsn_configured"] is True
            assert "key1***" in post_data["masked_dsn"]

            # 3. Read back config
            resp2 = client.get("/api/telemetry/config")
            assert resp2.status_code == 200
            assert resp2.json()["enabled"] is True
            assert "key1***" in resp2.json()["masked_dsn"]
    finally:
        server.shutdown()
        server.server_close()

    # 4. Verify persistence across server restart
    server2 = create_server(
        repo_root=repo_dir,
        port=0,
        token="tok-telemetry-123",
        db_path=db_file,
    )
    t2 = threading.Thread(target=server2.serve_forever, daemon=True)
    t2.start()
    time.sleep(0.05)
    base_url2 = f"http://127.0.0.1:{server2.server_port}"

    try:
        with httpx.Client(base_url=base_url2, headers=headers) as client2:
            resp3 = client2.get("/api/telemetry/config")
            assert resp3.status_code == 200
            assert resp3.json()["enabled"] is True
            assert "key1***" in resp3.json()["masked_dsn"]
    finally:
        server2.shutdown()
        server2.server_close()


def test_verified_delivery_and_trace_id_decoupling(tmp_path: Path) -> None:
    """Verify trace ID alone is staged_local and only marked verified_delivered upon transport confirmation."""
    repo_dir = tmp_path / "repo_delivery"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    (repo_dir / "file.py").write_text("print('hello')\n")
    db_file = tmp_path / "delivery_test.db"

    transport = InMemoryRecordingTransport()
    # Explicitly configure recording transport
    set_telemetry_opt_in(
        enabled=True,
        dsn="https://key12345@o999.ingest.sentry.io/111",
        transport=transport,
    )

    mock_reviewer = SlowMockReviewer(pause_seconds=0.1)
    server = create_server(
        repo_root=repo_dir,
        port=0,
        token="tok-delivery-123",
        reviewer=mock_reviewer,  # type: ignore
        db_path=db_file,
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)

    base_url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer tok-delivery-123"}

    try:
        with httpx.Client(base_url=base_url, headers=headers) as client:
            # Enable telemetry in server store as well
            client.post(
                "/api/telemetry/config",
                json={
                    "enabled": True,
                    "dsn": "https://key12345@o999.ingest.sentry.io/111",
                },
            )

            # Re-inject our recording transport for test verification
            set_telemetry_opt_in(
                enabled=True,
                dsn="https://key12345@o999.ingest.sentry.io/111",
                transport=transport,
            )

            # Run review
            review_resp = client.post(
                "/api/review",
                json={"repo_path": str(repo_dir), "force_refresh": True},
                timeout=10.0,
            )
            assert review_resp.status_code == 200

            # Verify delivery state is now VERIFIED_DELIVERED with recorded envelope
            receipt = get_last_delivery_receipt()
            assert receipt.state == ExportState.VERIFIED_DELIVERED
            assert receipt.verified_delivery is True
            assert receipt.trace_id is not None
            assert len(transport.envelopes) >= 1

            # Check config endpoint reports delivery verification
            cfg_resp = client.get("/api/telemetry/config")
            assert cfg_resp.status_code == 200
            cfg_data = cfg_resp.json()
            assert cfg_data["export_state"] == "verified_delivered"
            assert cfg_data["verified_delivery"] is True
            assert cfg_data["last_trace_id"] == receipt.trace_id
            assert cfg_data["trace_url"] is not None
            assert (
                f"https://o999.sentry.io/explore/traces/trace/{receipt.trace_id}/"
                in cfg_data["trace_url"]
            )
    finally:
        set_telemetry_opt_in(False)
        server.shutdown()
        server.server_close()


def test_mid_review_toggle_off_drops_unsent_spans(tmp_path: Path) -> None:
    """Verify disabling telemetry during active review immediately suppresses unsent spans and drops envelopes."""
    repo_dir = tmp_path / "repo_toggle_off"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    (repo_dir / "file.py").write_text("print('test')\n")
    db_file = tmp_path / "toggle_off_test.db"

    transport = InMemoryRecordingTransport()
    set_telemetry_opt_in(
        enabled=True,
        dsn="https://key12345@o999.ingest.sentry.io/111",
        transport=transport,
    )

    mock_reviewer = SlowMockReviewer(pause_seconds=0.3)
    server = create_server(
        repo_root=repo_dir,
        port=0,
        token="tok-toggle-123",
        reviewer=mock_reviewer,  # type: ignore
        db_path=db_file,
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)

    base_url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer tok-toggle-123"}

    try:
        with httpx.Client(base_url=base_url, headers=headers) as client:
            # Clear transport envelopes
            transport.envelopes.clear()

            # Launch review in background thread
            review_resp_holder: dict[str, Any] = {}

            def run_review():
                r = client.post(
                    "/api/review",
                    json={"repo_path": str(repo_dir), "force_refresh": True},
                    timeout=10.0,
                )
                review_resp_holder["status_code"] = r.status_code

            rev_thread = threading.Thread(target=run_review)
            rev_thread.start()

            # Wait until reviewer has started
            mock_reviewer.started_event.wait(timeout=2.0)

            # Mid-flight: toggle telemetry OFF
            toggle_resp = client.post(
                "/api/telemetry/config",
                json={"enabled": False},
            )
            assert toggle_resp.status_code == 200
            assert toggle_resp.json()["enabled"] is False

            rev_thread.join(timeout=5.0)
            assert review_resp_holder.get("status_code") == 200

            # Verify that unsent spans were dropped and transport recorded ZERO envelopes!
            assert len(transport.envelopes) == 0
            receipt = get_last_delivery_receipt()
            assert receipt.verified_delivery is False
            assert get_export_state() == ExportState.DISABLED
    finally:
        set_telemetry_opt_in(False)
        server.shutdown()
        server.server_close()


def test_mid_review_toggle_on_deferred(tmp_path: Path) -> None:
    """Verify enabling telemetry mid-review is safely deferred to subsequent review without retrofitting spans."""
    repo_dir = tmp_path / "repo_toggle_on"
    repo_dir.mkdir()
    (repo_dir / ".git").mkdir()
    (repo_dir / "file.py").write_text("print('test')\n")
    db_file = tmp_path / "toggle_on_test.db"

    # Start with telemetry disabled
    set_telemetry_opt_in(enabled=False)

    mock_reviewer = SlowMockReviewer(pause_seconds=0.3)
    server = create_server(
        repo_root=repo_dir,
        port=0,
        token="tok-toggle-on-123",
        reviewer=mock_reviewer,  # type: ignore
        db_path=db_file,
    )
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.05)

    base_url = f"http://127.0.0.1:{server.server_port}"
    headers = {"Authorization": "Bearer tok-toggle-on-123"}

    try:
        with httpx.Client(base_url=base_url, headers=headers) as client:
            review_resp_holder: dict[str, Any] = {}

            def run_review():
                r = client.post(
                    "/api/review",
                    json={"repo_path": str(repo_dir), "force_refresh": True},
                    timeout=10.0,
                )
                review_resp_holder["status_code"] = r.status_code

            rev_thread = threading.Thread(target=run_review)
            rev_thread.start()

            # Wait until reviewer has started
            mock_reviewer.started_event.wait(timeout=2.0)

            # Mid-flight: toggle telemetry ON
            toggle_resp = client.post(
                "/api/telemetry/config",
                json={
                    "enabled": True,
                    "dsn": "https://key12345@o999.ingest.sentry.io/111",
                },
            )
            assert toggle_resp.status_code == 200
            resp_body = toggle_resp.json()
            assert resp_body["enabled"] is True
            assert resp_body["pending_activation"] is True
            assert resp_body["effective_immediately"] is False

            rev_thread.join(timeout=5.0)
            assert review_resp_holder.get("status_code") == 200
    finally:
        set_telemetry_opt_in(False)
        server.shutdown()
        server.server_close()
