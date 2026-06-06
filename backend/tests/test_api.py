import io
import os
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST_DB = ROOT / "test_atm_media.db"
TEST_UPLOADS = ROOT / "tmp_uploads"

if TEST_DB.exists():
    TEST_DB.unlink()
if TEST_UPLOADS.exists():
    shutil.rmtree(TEST_UPLOADS)

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["UPLOAD_DIR"] = str(TEST_UPLOADS)
os.environ["JWT_SECRET_KEY"] = "test-secret"
os.environ["ADMIN_USERNAME"] = "admin"
os.environ["ADMIN_PASSWORD"] = "secret123"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402


def make_zip(files: dict[str, bytes]) -> io.BytesIO:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    buffer.seek(0)
    return buffer


def login(client: TestClient) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"username": "admin", "password": "secret123"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_health() -> None:
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


def test_admin_can_download_agent_exe_when_available() -> None:
    exe_path = ROOT.parent / "agent" / "dist" / "atm-agent.exe"
    original = exe_path.read_bytes() if exe_path.exists() else None
    exe_path.parent.mkdir(parents=True, exist_ok=True)
    exe_path.write_bytes(b"fake-exe")
    try:
        with TestClient(app) as client:
            headers = login(client)
            response = client.get("/api/agent-downloads/exe", headers=headers)
            assert response.status_code == 200
            assert response.content == b"fake-exe"
            assert "atm-agent.exe" in response.headers["content-disposition"]
    finally:
        if original is None:
            exe_path.unlink(missing_ok=True)
        else:
            exe_path.write_bytes(original)


def test_admin_can_create_atm_and_agent_can_heartbeat() -> None:
    with TestClient(app) as client:
        headers = login(client)
        response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-001", "name": "Main Lobby", "vpn_ip": "10.10.0.11", "branch": "HQ"},
            headers=headers,
        )
        assert response.status_code == 201
        api_key = response.json()["api_key"]

        agent_headers = {"X-ATM-ID": "ATM-001", "X-API-Key": api_key}
        heartbeat = client.post(
            "/api/agent/heartbeat",
            json={"current_version": "v0", "latency_ms": 87},
            headers=agent_headers,
        )
        assert heartbeat.status_code == 200
        assert heartbeat.json()["ok"] is True

        atm = client.get("/api/atms/ATM-001", headers=headers)
        assert atm.status_code == 200
        assert atm.json()["latency_ms"] == 87

        diagnostics = client.get("/api/atms/ATM-001/diagnostics", headers=headers)
        assert diagnostics.status_code == 200
        assert diagnostics.json()["reporting_status"] == "reporting"
        assert diagnostics.json()["summary"] == "Agent is reporting normally"


def test_admin_can_manage_users_and_page_visibility() -> None:
    with TestClient(app) as client:
        headers = login(client)
        pages = client.get("/api/users/pages", headers=headers)
        assert pages.status_code == 200
        page_map = {page["id"]: page["label"] for page in pages.json()}
        assert page_map["dashboard"] == "لوحة المراقبة"
        assert page_map["atms"] == "الصرافات"
        assert page_map["cash"] == "مراقبة النقد"
        assert page_map["notifications"] == "مركز التنبيهات"
        assert page_map["agent-downloads"] == "Agent Downloads"
        assert page_map["logs"] == "السجلات"
        assert page_map["settings"] == "الإعدادات"
        assert page_map["users"] == "إدارة المستخدمين"

        created = client.post(
            "/api/users",
            json={
                "username": "operator1",
                "password": "operator123",
                "role": "operator",
                "allowed_pages": ["dashboard", "atms", "cash", "notifications", "logs"],
                "is_active": True,
            },
            headers=headers,
        )
        assert created.status_code == 201
        assert created.json()["allowed_pages"] == ["dashboard", "atms", "cash", "notifications", "logs"]

        operator_login = client.post("/api/auth/login", json={"username": "operator1", "password": "operator123"})
        assert operator_login.status_code == 200
        operator_payload = operator_login.json()
        assert operator_payload["user"]["allowed_pages"] == ["dashboard", "atms", "cash", "notifications", "logs"]
        operator_headers = {"Authorization": f"Bearer {operator_payload['access_token']}"}

        denied = client.get("/api/users", headers=operator_headers)
        assert denied.status_code == 403

        updated = client.put(
            f"/api/users/{created.json()['id']}",
            json={"allowed_pages": ["dashboard", "packages"]},
            headers=headers,
        )
        assert updated.status_code == 200
        assert updated.json()["allowed_pages"] == ["dashboard", "packages"]


def test_atm_diagnostics_show_never_reported_before_heartbeat() -> None:
    with TestClient(app) as client:
        headers = login(client)
        response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-DIAG", "name": "Diag ATM", "vpn_ip": "10.10.0.31", "branch": "HQ"},
            headers=headers,
        )
        assert response.status_code == 201

        diagnostics = client.get("/api/atms/ATM-DIAG/diagnostics", headers=headers)
        assert diagnostics.status_code == 200
        payload = diagnostics.json()
        assert payload["reporting_status"] == "never_reported"
        assert payload["summary"] == "No heartbeat received yet"


def test_upload_assign_check_download_and_report_success() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-002", "name": "Branch 2", "vpn_ip": "10.10.0.12", "branch": "North"},
            headers=headers,
        )
        assert atm_response.status_code == 201
        api_key = atm_response.json()["api_key"]
        agent_headers = {"X-ATM-ID": "ATM-002", "X-API-Key": api_key}

        zip_buffer = make_zip({"screen/welcome.png": b"fake-png-bytes"})
        upload = client.post(
            "/api/packages/upload",
            data={"version": "media-test-1", "notes": "test package"},
            files={"file": ("media.zip", zip_buffer, "application/zip")},
            headers=headers,
        )
        assert upload.status_code == 201
        package = upload.json()

        assign = client.post(f"/api/packages/{package['id']}/assign", json={"atm_ids": ["ATM-002"]}, headers=headers)
        assert assign.status_code == 200
        assert assign.json()["assigned"] == 1

        check = client.get("/api/agent/check-update", headers=agent_headers)
        assert check.status_code == 200
        assert check.json()["update_available"] is True
        assert check.json()["has_update"] is True
        assert check.json()["sha256"] == package["sha256"]

        download = client.get(f"/api/agent/download/{package['id']}", headers=agent_headers)
        assert download.status_code == 200
        assert download.content

        progress = client.post(
            "/api/agent/progress",
            json={
                "package_id": package["id"],
                "phase": "downloading",
                "progress_percent": 42,
                "message": "Downloading package",
                "bytes_downloaded": 42,
                "total_bytes": 100,
            },
            headers=agent_headers,
        )
        assert progress.status_code == 200

        progress_details = client.get(f"/api/packages/{package['id']}", headers=headers)
        assert progress_details.status_code == 200
        assert progress_details.json()["targets"][0]["progress_percent"] == 42
        assert progress_details.json()["targets"][0]["progress_phase"] == "downloading"

        report = client.post(
            "/api/agent/report-result",
            json={"package_id": package["id"], "status": "success", "message": "ok"},
            headers=agent_headers,
        )
        assert report.status_code == 200

        details = client.get(f"/api/packages/{package['id']}", headers=headers)
        assert details.status_code == 200
        assert details.json()["targets"][0]["status"] == "applied"


def test_agent_config_ack_and_atm_settings_version() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-CONFIG", "name": "Config ATM", "vpn_ip": "10.10.0.20", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201
        api_key = atm_response.json()["api_key"]
        agent_headers = {"X-ATM-ID": "ATM-CONFIG", "X-API-Key": api_key}

        before = atm_response.json()["atm"]["config_version"]
        update = client.put(
            "/api/atms/ATM-CONFIG",
            json={
                "media_path": "C:/ATM/NewMedia",
                "backup_path": "C:/ATM/NewBackup",
                "temp_path": "C:/ATM/NewTemp",
                "xfs_profile": "grg",
                "xfs_logical_service": "CDM",
            },
            headers=headers,
        )
        assert update.status_code == 200
        assert update.json()["config_version"] == before + 1

        config = client.get("/api/agent/config", headers=agent_headers)
        assert config.status_code == 200
        assert config.json()["media_path"] == "C:/ATM/NewMedia"
        assert config.json()["modules"]["media_update"]["enabled"] is True
        assert config.json()["modules"]["cash_monitoring"]["enabled"] is False
        assert config.json()["modules"]["cash_monitoring"]["atm_cash_mode"] == "DISPENSE_ONLY"
        assert config.json()["modules"]["cash_monitoring"]["xfs_profile"] == "grg"
        assert config.json()["modules"]["cash_monitoring"]["xfs_logical_service"] == "CDM"
        assert config.json()["modules"]["cash_monitoring"]["cash_layout"][0]["cassette_no"] == 1

        ack = client.post(
            "/api/agent/config-ack",
            json={
                "atm_id": "ATM-CONFIG",
                "applied_config_version": config.json()["config_version"],
                "success": True,
                "enabled_modules": ["media_update"],
            },
            headers=agent_headers,
        )
        assert ack.status_code == 200

        after = client.get("/api/atms/ATM-CONFIG", headers=headers)
        assert after.status_code == 200
        assert after.json()["applied_config_version"] == config.json()["config_version"]
        assert after.json()["module_status_json"]["media_update"] == "configured"


def test_agent_heartbeat_records_module_statuses() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-MODULES", "name": "Modules ATM", "vpn_ip": "10.10.0.41", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-MODULES", "X-API-Key": atm_response.json()["api_key"]}

        heartbeat = client.post(
            "/api/agent/heartbeat",
            json={
                "atm_id": "ATM-MODULES",
                "agent_version": "2.0.0",
                "enabled_modules": ["media_update", "cash_monitoring"],
                "module_statuses": {"media_update": "running", "cash_monitoring": "running"},
            },
            headers=agent_headers,
        )
        assert heartbeat.status_code == 200

        atm = client.get("/api/atms/ATM-MODULES", headers=headers)
        assert atm.status_code == 200
        assert atm.json()["agent_version"] == "2.0.0"
        assert atm.json()["module_status_json"]["cash_monitoring"] == "running"


def test_switch_probe_request_and_agent_result() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-SWITCH",
                "name": "Switch ATM",
                "vpn_ip": "10.10.0.48",
                "branch": "HQ",
                "switch_probe_host": "172.16.25.75",
                "switch_probe_port": 10200,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-SWITCH", "X-API-Key": atm_response.json()["api_key"]}

        request = client.post("/api/atms/ATM-SWITCH/switch-probe", headers=headers)
        assert request.status_code == 202
        probe_id = request.json()["id"]
        assert request.json()["host"] == "172.16.25.75"
        assert request.json()["port"] == 10200
        assert request.json()["status"] == "pending"

        pending = client.get("/api/agent/switch-probe", headers=agent_headers)
        assert pending.status_code == 200
        assert pending.json()["has_probe"] is True
        assert pending.json()["probe"]["id"] == probe_id
        assert pending.json()["probe"]["status"] == "running"

        result = client.post(
            "/api/agent/switch-probe-result",
            json={"probe_id": probe_id, "status": "success", "latency_ms": 33},
            headers=agent_headers,
        )
        assert result.status_code == 200

        atm = client.get("/api/atms/ATM-SWITCH", headers=headers)
        assert atm.status_code == 200
        assert atm.json()["last_switch_probe_status"] == "success"
        assert atm.json()["last_switch_probe_latency_ms"] == 33

        history = client.get("/api/atms/ATM-SWITCH/switch-probes", headers=headers)
        assert history.status_code == 200
        assert history.json()[0]["status"] == "success"


def test_periodic_switch_probe_result_updates_atm_and_sends_transition_notification(monkeypatch) -> None:
    sent_messages = []

    def fake_send_email(settings, subject, body, recipient_email=None, html_body=None):
        sent_messages.append(
            {
                "subject": subject,
                "body": body,
                "recipient_email": recipient_email,
                "html_body": html_body,
            }
        )

    monkeypatch.setattr("app.services.notification_service.send_email", fake_send_email)

    with TestClient(app) as client:
        headers = login(client)
        settings = client.put(
            "/api/notifications/settings",
            json={
                "enabled": True,
                "recipient_email": "ops@example.com",
                "sender_email": "atm@example.com",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_security": "starttls",
            },
            headers=headers,
        )
        assert settings.status_code == 200

        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-SWITCH-AUTO",
                "name": "Auto Switch ATM",
                "vpn_ip": "10.10.0.50",
                "branch": "HQ",
                "switch_probe_host": "172.16.25.75",
                "switch_probe_port": 10200,
                "switch_probe_interval_seconds": 30,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-SWITCH-AUTO", "X-API-Key": atm_response.json()["api_key"]}

        config = client.get("/api/agent/config", headers=agent_headers)
        assert config.status_code == 200
        assert config.json()["switch_probe_interval_seconds"] == 30

        failed = client.post(
            "/api/agent/switch-probe-snapshot",
            json={
                "status": "failed",
                "latency_ms": 5000,
                "error_message": "timed out",
                "host": "172.16.25.75",
                "port": 10200,
            },
            headers=agent_headers,
        )
        assert failed.status_code == 200

        repeated_failed = client.post(
            "/api/agent/switch-probe-snapshot",
            json={
                "status": "failed",
                "latency_ms": 5000,
                "error_message": "timed out",
                "host": "172.16.25.75",
                "port": 10200,
            },
            headers=agent_headers,
        )
        assert repeated_failed.status_code == 200

        atm = client.get("/api/atms/ATM-SWITCH-AUTO", headers=headers)
        assert atm.status_code == 200
        assert atm.json()["last_switch_probe_status"] == "failed"
        assert atm.json()["last_switch_probe_error"] == "timed out"

        history = client.get("/api/atms/ATM-SWITCH-AUTO/switch-probes", headers=headers)
        assert history.status_code == 200
        assert history.json()[0]["requested_by"] == "agent:auto"
        assert history.json()[0]["status"] == "failed"

        deliveries = client.get("/api/notifications/deliveries", headers=headers)
        assert deliveries.status_code == 200
        switch_deliveries = [item for item in deliveries.json() if item["event_type"] == "SWITCH_DISCONNECTED"]
        assert len(switch_deliveries) == 1
        assert sent_messages and sent_messages[0]["recipient_email"] == "ops@example.com"


def test_switch_probe_disconnect_notification_can_be_disabled(monkeypatch) -> None:
    sent_messages = []

    def fake_send_email(settings, subject, body, recipient_email=None, html_body=None):
        sent_messages.append(
            {
                "subject": subject,
                "body": body,
                "recipient_email": recipient_email,
                "html_body": html_body,
            }
        )

    monkeypatch.setattr("app.services.notification_service.send_email", fake_send_email)

    with TestClient(app) as client:
        headers = login(client)
        settings = client.put(
            "/api/notifications/settings",
            json={
                "enabled": True,
                "recipient_email": "ops@example.com",
                "sender_email": "atm@example.com",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_security": "starttls",
                "notify_switch_disconnected": False,
            },
            headers=headers,
        )
        assert settings.status_code == 200
        assert settings.json()["notify_switch_disconnected"] is False

        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-SWITCH-NO-MAIL",
                "name": "No Mail Switch ATM",
                "vpn_ip": "10.10.0.51",
                "branch": "HQ",
                "switch_probe_host": "172.16.25.75",
                "switch_probe_port": 10200,
                "switch_probe_interval_seconds": 30,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-SWITCH-NO-MAIL", "X-API-Key": atm_response.json()["api_key"]}

        failed = client.post(
            "/api/agent/switch-probe-snapshot",
            json={
                "status": "failed",
                "latency_ms": 5000,
                "error_message": "timed out",
                "host": "172.16.25.75",
                "port": 10200,
            },
            headers=agent_headers,
        )
        assert failed.status_code == 200

        deliveries = client.get("/api/notifications/deliveries", headers=headers)
        assert deliveries.status_code == 200
        switch_deliveries = [
            item
            for item in deliveries.json()
            if item["event_type"] == "SWITCH_DISCONNECTED" and "No Mail Switch ATM" in item["subject"]
        ]
        assert switch_deliveries == []
        assert sent_messages == []


def test_switch_probe_disconnect_can_send_whatsapp_without_smtp(monkeypatch) -> None:
    sent_messages = []

    def fake_send_whatsapp(settings, recipient, message):
        sent_messages.append({"recipient": recipient, "message": message})

    monkeypatch.setattr("app.services.notification_service.send_whatsapp", fake_send_whatsapp)

    with TestClient(app) as client:
        headers = login(client)
        settings = client.put(
            "/api/notifications/settings",
            json={
                "enabled": True,
                "whatsapp_enabled": True,
                "whatsapp_gateway_url": "http://127.0.0.1:3020",
                "whatsapp_default_recipient": "967777777777",
                "notify_switch_disconnected": True,
            },
            headers=headers,
        )
        assert settings.status_code == 200
        assert settings.json()["is_whatsapp_configured"] is True

        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-SWITCH-WA",
                "name": "WhatsApp Switch ATM",
                "vpn_ip": "10.10.0.52",
                "branch": "HQ",
                "switch_probe_host": "172.16.25.75",
                "switch_probe_port": 10200,
                "switch_probe_interval_seconds": 30,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-SWITCH-WA", "X-API-Key": atm_response.json()["api_key"]}

        failed = client.post(
            "/api/agent/switch-probe-snapshot",
            json={
                "status": "failed",
                "latency_ms": 5000,
                "error_message": "timed out",
                "host": "172.16.25.75",
                "port": 10200,
            },
            headers=agent_headers,
        )
        assert failed.status_code == 200

        deliveries = client.get("/api/notifications/deliveries", headers=headers)
        assert deliveries.status_code == 200
        whatsapp_deliveries = [
            item
            for item in deliveries.json()
            if item["event_type"] == "SWITCH_DISCONNECTED"
            and item["channel"] == "whatsapp"
            and "WhatsApp Switch ATM" in item["subject"]
        ]
        assert len(whatsapp_deliveries) == 1
        assert whatsapp_deliveries[0]["recipient_email"] == "967777777777"
        assert sent_messages and sent_messages[0]["recipient"] == "967777777777"


def test_switch_probe_disconnect_sends_whatsapp_to_default_group_and_one_atm_recipient(monkeypatch) -> None:
    sent_messages = []

    def fake_send_whatsapp(settings, recipient, message):
        sent_messages.append({"recipient": recipient, "message": message})

    monkeypatch.setattr("app.services.notification_service.send_whatsapp", fake_send_whatsapp)

    with TestClient(app) as client:
        headers = login(client)
        settings = client.put(
            "/api/notifications/settings",
            json={
                "enabled": True,
                "whatsapp_enabled": True,
                "whatsapp_gateway_url": "http://127.0.0.1:3020",
                "whatsapp_default_recipients": ["967700000001", "967700000002"],
                "notify_switch_disconnected": True,
            },
            headers=headers,
        )
        assert settings.status_code == 200
        assert settings.json()["whatsapp_default_recipient"] == "967700000001"
        assert settings.json()["whatsapp_default_recipients"] == ["967700000001", "967700000002"]

        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-SWITCH-WA-MULTI",
                "name": "WhatsApp Multi ATM",
                "vpn_ip": "10.10.0.53",
                "branch": "HQ",
                "switch_probe_host": "172.16.25.75",
                "switch_probe_port": 10200,
                "switch_probe_interval_seconds": 30,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201

        recipients = client.put(
            "/api/notifications/recipients",
            json={
                "recipients": [
                    {
                        "atm_id": "ATM-SWITCH-WA-MULTI",
                        "enabled": True,
                        "whatsapp_numbers": ["967711111111", "967722222222"],
                    }
                ]
            },
            headers=headers,
        )
        assert recipients.status_code == 200
        row = [item for item in recipients.json() if item["atm_id"] == "ATM-SWITCH-WA-MULTI"][0]
        assert row["whatsapp_numbers"] == ["967711111111"]
        assert row["effective_whatsapp_numbers"] == ["967700000001", "967700000002", "967711111111"]

        agent_headers = {"X-ATM-ID": "ATM-SWITCH-WA-MULTI", "X-API-Key": atm_response.json()["api_key"]}
        failed = client.post(
            "/api/agent/switch-probe-snapshot",
            json={
                "status": "failed",
                "latency_ms": 5000,
                "error_message": "timed out",
                "host": "172.16.25.75",
                "port": 10200,
            },
            headers=agent_headers,
        )
        assert failed.status_code == 200

        deliveries = client.get("/api/notifications/deliveries", headers=headers)
        assert deliveries.status_code == 200
        whatsapp_deliveries = [
            item
            for item in deliveries.json()
            if item["event_type"] == "SWITCH_DISCONNECTED"
            and item["channel"] == "whatsapp"
            and "WhatsApp Multi ATM" in item["subject"]
        ]
        assert {item["recipient_email"] for item in whatsapp_deliveries} == {
            "967700000001",
            "967700000002",
            "967711111111",
        }
        assert {item["recipient"] for item in sent_messages} == {
            "967700000001",
            "967700000002",
            "967711111111",
        }


def test_whatsapp_status_transition_sends_email_alert(monkeypatch) -> None:
    sent_messages = []
    gateway_statuses = [
        {"ready": True, "status": "ready"},
        {"ready": False, "status": "disconnected", "message": "phone logged out"},
    ]

    def fake_gateway_request(settings, path, method="GET", payload=None):
        assert path == "/status"
        return gateway_statuses.pop(0)

    def fake_send_email(settings, subject, body, recipient_email=None, html_body=None):
        sent_messages.append(
            {
                "subject": subject,
                "body": body,
                "recipient_email": recipient_email,
                "html_body": html_body,
            }
        )

    monkeypatch.setattr("app.services.notification_service.whatsapp_gateway_request", fake_gateway_request)
    monkeypatch.setattr("app.services.notification_service.send_email", fake_send_email)

    with TestClient(app) as client:
        headers = login(client)
        settings = client.put(
            "/api/notifications/settings",
            json={
                "enabled": True,
                "recipient_email": "ops@example.com",
                "sender_email": "atm@example.com",
                "smtp_host": "smtp.example.com",
                "smtp_port": 587,
                "smtp_security": "starttls",
                "whatsapp_enabled": True,
                "whatsapp_gateway_url": "http://127.0.0.1:3020",
                "whatsapp_default_recipient": "967777777777",
                "notify_whatsapp_disconnected": True,
            },
            headers=headers,
        )
        assert settings.status_code == 200

        ready = client.get("/api/notifications/whatsapp/status", headers=headers)
        assert ready.status_code == 200
        assert ready.json()["status"] == "ready"

        disconnected = client.get("/api/notifications/whatsapp/status", headers=headers)
        assert disconnected.status_code == 200
        assert disconnected.json()["status"] == "disconnected"

        deliveries = client.get("/api/notifications/deliveries", headers=headers)
        assert deliveries.status_code == 200
        whatsapp_alerts = [item for item in deliveries.json() if item["event_type"] == "WHATSAPP_DISCONNECTED"]
        assert len(whatsapp_alerts) == 1
        assert whatsapp_alerts[0]["channel"] == "email"
        assert sent_messages and sent_messages[0]["recipient_email"] == "ops@example.com"


def test_switch_probe_new_target_supersedes_existing_pending_probe() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-SWITCH-CHANGE",
                "name": "Switch Change ATM",
                "vpn_ip": "10.10.0.49",
                "branch": "HQ",
                "switch_probe_host": "172.16.25.75",
                "switch_probe_port": 10200,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201

        first = client.post("/api/atms/ATM-SWITCH-CHANGE/switch-probe", headers=headers)
        assert first.status_code == 202
        assert first.json()["host"] == "172.16.25.75"

        second = client.post(
            "/api/atms/ATM-SWITCH-CHANGE/switch-probe",
            json={"host": "172.16.75.25", "port": 10200},
            headers=headers,
        )
        assert second.status_code == 202
        assert second.json()["id"] != first.json()["id"]
        assert second.json()["host"] == "172.16.75.25"

        history = client.get("/api/atms/ATM-SWITCH-CHANGE/switch-probes", headers=headers)
        assert history.status_code == 200
        statuses = {item["id"]: item["status"] for item in history.json()}
        assert statuses[first.json()["id"]] == "cancelled"
        assert statuses[second.json()["id"]] == "pending"

        atm = client.get("/api/atms/ATM-SWITCH-CHANGE", headers=headers)
        assert atm.status_code == 200
        assert atm.json()["switch_probe_host"] == "172.16.75.25"


def test_cash_layout_validation_allows_duplicate_denomination_but_not_duplicate_cassette() -> None:
    with TestClient(app) as client:
        headers = login(client)
        valid = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-LAYOUT-OK",
                "name": "Layout OK",
                "vpn_ip": "10.10.0.45",
                "branch": "HQ",
                "cash_layout": [
                    {"cassette_no": 1, "currency": "YER", "denomination": 1000},
                    {"cassette_no": 2, "currency": "YER", "denomination": 1000},
                ],
            },
            headers=headers,
        )
        assert valid.status_code == 201

        duplicate = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-LAYOUT-DUP",
                "name": "Layout Dup",
                "vpn_ip": "10.10.0.46",
                "branch": "HQ",
                "cash_layout": [
                    {"cassette_no": 1, "currency": "YER", "denomination": 1000},
                    {"cassette_no": 1, "currency": "USD", "denomination": 100},
                ],
            },
            headers=headers,
        )
        assert duplicate.status_code == 422

        bad_denomination = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-LAYOUT-BAD",
                "name": "Layout Bad",
                "vpn_ip": "10.10.0.47",
                "branch": "HQ",
                "cash_layout": [
                    {"cassette_no": 1, "currency": "USD", "denomination": 50},
                ],
            },
            headers=headers,
        )
        assert bad_denomination.status_code == 422


def test_cash_snapshot_updates_units_and_alerts() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-CASH",
                "name": "Cash ATM",
                "vpn_ip": "10.10.0.42",
                "branch": "HQ",
                "cash_monitoring_enabled": True,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-CASH", "X-API-Key": atm_response.json()["api_key"]}

        snapshot = client.post(
            "/api/agent/cash-snapshot",
            json={
                "atm_id": "ATM-CASH",
                "source": "xfs_cdm",
                "atm_cash_mode": "DISPENSE_ONLY",
                "read_at": "2026-05-25T10:30:00Z",
                "cash_units": [
                    {
                        "cassette_no": 1,
                        "cassette_id": "CST01",
                        "cassette_name": "Dispense Cassette 1",
                        "reported_currency": "YER",
                        "reported_denomination": 1000,
                        "initial_count": 2000,
                        "current_count": 80,
                        "reject_count": 0,
                        "retract_count": 0,
                        "dispensed_count": 1920,
                        "presented_count": 1920,
                        "status": "LOW",
                        "physical_status": "PRESENT",
                    },
                    {
                        "cassette_no": 2,
                        "cassette_id": "CST02",
                        "cassette_name": "Dispense Cassette 2",
                        "reported_currency": "YER",
                        "reported_denomination": 1000,
                        "initial_count": 2000,
                        "current_count": 250,
                        "reject_count": 0,
                        "retract_count": 0,
                        "dispensed_count": 1750,
                        "presented_count": 1750,
                        "status": "LOW",
                        "physical_status": "PRESENT",
                    },
                    {
                        "cassette_no": 3,
                        "cassette_id": "CST03",
                        "cassette_name": "Dispense Cassette 3",
                        "reported_currency": "YER",
                        "reported_denomination": 1000,
                        "initial_count": 2000,
                        "current_count": 0,
                        "reject_count": 0,
                        "retract_count": 0,
                        "dispensed_count": 2000,
                        "presented_count": 2000,
                        "status": "EMPTY",
                        "physical_status": "PRESENT",
                    }
                ],
                "reject_retract": {
                    "reject_count": 90,
                    "retract_count": 1,
                    "reject_status": "OK",
                    "retract_status": "OK",
                    "reject_max_capacity": 100,
                    "retract_max_capacity": 50,
                },
            },
            headers=agent_headers,
        )
        assert snapshot.status_code == 200

        details = client.get("/api/cash/atms/ATM-CASH", headers=headers)
        assert details.status_code == 200
        assert details.json()["units"][0]["current_count"] == 80
        assert details.json()["units"][0]["cassette_no"] == 1
        assert details.json()["reject_retract"]["reject_count"] == 90
        assert details.json()["reject_retract"]["retract_count"] == 1
        alert_types = {alert["alert_type"] for alert in details.json()["alerts"]}
        assert {"CASH_LOW", "CASH_CRITICAL", "CASH_EMPTY", "REJECT_BIN_HIGH", "RETRACT_OCCURRED"}.issubset(alert_types)
        verification = details.json()["verification"]
        assert verification["status"] == "mismatch"
        assert verification["matched"] is False
        assert verification["matched_units"] == 3
        assert any(issue["code"] == "MISSING_READING" and issue["cassette_no"] == 4 for issue in verification["issues"])

        layout_update = client.put(
            "/api/atms/ATM-CASH",
            json={
                "cash_layout": [
                    {"cassette_no": 1, "currency": "YER", "denomination": 1000},
                    {"cassette_no": 2, "currency": "YER", "denomination": 1000},
                    {"cassette_no": 3, "currency": "USD", "denomination": 100, "low_threshold": 100, "critical_threshold": 30},
                    {"cassette_no": 4, "currency": "SAR", "denomination": 100, "low_threshold": 100, "critical_threshold": 30},
                ]
            },
            headers=headers,
        )
        assert layout_update.status_code == 200

        updated_details = client.get("/api/cash/atms/ATM-CASH", headers=headers)
        assert updated_details.status_code == 200
        cassette_three = next(unit for unit in updated_details.json()["units"] if unit["cassette_no"] == 3)
        assert cassette_three["expected_currency"] == "USD"
        assert cassette_three["expected_denomination"] == 100
        assert cassette_three["low_threshold"] == 100
        assert cassette_three["critical_threshold"] == 30
        assert cassette_three["reported_currency"] == "USD"
        assert cassette_three["reported_denomination"] == 100
        assert cassette_three["layout_match_status"] == "MATCH"
        updated_verification = updated_details.json()["verification"]
        issue_codes = {issue["code"] for issue in updated_verification["issues"]}
        assert updated_verification["status"] == "mismatch"
        assert "MISSING_READING" in issue_codes
        assert "CURRENCY_MISMATCH" not in issue_codes
        assert "DENOMINATION_MISMATCH" not in issue_codes

        summary = client.get("/api/cash/summary", headers=headers)
        assert summary.status_code == 200
        assert summary.json()["open_alerts"] >= 1
        assert summary.json()["cash_low_atms"] >= 1
        assert summary.json()["cash_critical_atms"] >= 1
        assert summary.json()["cash_empty_atms"] >= 1
        assert len(summary.json()["low_cash_atms"]) >= 1
        assert len(summary.json()["empty_cash_atms"]) >= 1


def test_cash_snapshot_ignores_suspicious_regression() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-CASH-GUARD",
                "name": "Cash Guard",
                "vpn_ip": "10.10.0.55",
                "branch": "HQ",
                "cash_monitoring_enabled": True,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-CASH-GUARD", "X-API-Key": atm_response.json()["api_key"]}

        def snapshot(read_at: str, cassette_one: int, cassette_two: int) -> dict:
            return {
                "atm_id": "ATM-CASH-GUARD",
                "source": "xfs_cdm",
                "atm_cash_mode": "DISPENSE_ONLY",
                "read_at": read_at,
                "cash_units": [
                    {
                        "cassette_no": 1,
                        "cassette_id": "1",
                        "cassette_name": "Cash Bin 1",
                        "reported_currency": "YER",
                        "reported_denomination": 1000,
                        "initial_count": 2500,
                        "current_count": cassette_one,
                        "reject_count": 1,
                        "retract_count": 0,
                        "dispensed_count": max(0, 2500 - cassette_one),
                        "presented_count": max(0, 2500 - cassette_one),
                        "status": "OK" if cassette_one > 0 else "EMPTY",
                        "physical_status": "PRESENT",
                    },
                    {
                        "cassette_no": 2,
                        "cassette_id": "2",
                        "cassette_name": "Cash Bin 2",
                        "reported_currency": "YER",
                        "reported_denomination": 1000,
                        "initial_count": 2500,
                        "current_count": cassette_two,
                        "reject_count": 1,
                        "retract_count": 0,
                        "dispensed_count": max(0, 2500 - cassette_two),
                        "presented_count": max(0, 2500 - cassette_two),
                        "status": "OK" if cassette_two > 0 else "EMPTY",
                        "physical_status": "PRESENT",
                    },
                ],
                "reject_retract": {
                    "reject_count": 2,
                    "retract_count": 0,
                    "reject_status": "OK",
                    "retract_status": "OK",
                    "reject_max_capacity": 215,
                    "retract_max_capacity": 50,
                },
            }

        fresh = client.post(
            "/api/agent/cash-snapshot",
            json=snapshot("2026-05-25T10:00:00Z", 2304, 2304),
            headers=agent_headers,
        )
        assert fresh.status_code == 200

        suspicious = client.post(
            "/api/agent/cash-snapshot",
            json=snapshot("2026-05-25T10:05:00Z", 0, 0),
            headers=agent_headers,
        )
        assert suspicious.status_code == 200

        details = client.get("/api/cash/atms/ATM-CASH-GUARD", headers=headers)
        assert details.status_code == 200
        counts = {unit["cassette_no"]: unit["current_count"] for unit in details.json()["units"]}
        assert counts[1] == 2304
        assert counts[2] == 2304

        logs = client.get("/api/logs", headers=headers)
        assert logs.status_code == 200
        assert any(item["message"] == "Ignored suspicious cash snapshot regression" for item in logs.json())


def test_cash_snapshot_adjusts_future_agent_timestamp() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-CASH-FUTURE",
                "name": "Future Clock",
                "vpn_ip": "10.10.0.58",
                "branch": "HQ",
                "cash_monitoring_enabled": True,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-CASH-FUTURE", "X-API-Key": atm_response.json()["api_key"]}

        future_read_at = datetime.now(timezone.utc) + timedelta(hours=10)
        before_submit = datetime.now(timezone.utc) - timedelta(seconds=1)
        snapshot = client.post(
            "/api/agent/cash-snapshot",
            json={
                "atm_id": "ATM-CASH-FUTURE",
                "source": "xfs_cdm",
                "atm_cash_mode": "DISPENSE_ONLY",
                "read_at": future_read_at.isoformat(),
                "cash_units": [
                    {
                        "cassette_no": 1,
                        "cassette_id": "CST01",
                        "cassette_name": "Dispense Cassette 1",
                        "reported_currency": "YER",
                        "reported_denomination": 1000,
                        "initial_count": 2000,
                        "current_count": 1200,
                        "reject_count": 0,
                        "retract_count": 0,
                        "dispensed_count": 800,
                        "presented_count": 800,
                        "status": "OK",
                        "physical_status": "PRESENT",
                    }
                ],
            },
            headers=agent_headers,
        )
        after_submit = datetime.now(timezone.utc) + timedelta(seconds=1)
        assert snapshot.status_code == 200

        details = client.get("/api/cash/atms/ATM-CASH-FUTURE", headers=headers)
        assert details.status_code == 200
        stored_read_at = datetime.fromisoformat(details.json()["units"][0]["read_at"].replace("Z", "+00:00"))
        if stored_read_at.tzinfo is None:
            stored_read_at = stored_read_at.replace(tzinfo=timezone.utc)
        assert before_submit <= stored_read_at <= after_submit

        logs = client.get("/api/logs", headers=headers)
        assert logs.status_code == 200
        assert any(item["message"] == "Adjusted future cash snapshot timestamp" for item in logs.json())


def test_cash_snapshot_uses_configured_layout_values_over_atm_reported_money() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-CASH-MISMATCH",
                "name": "Cash Mismatch",
                "vpn_ip": "10.10.0.56",
                "branch": "HQ",
                "cash_monitoring_enabled": True,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-CASH-MISMATCH", "X-API-Key": atm_response.json()["api_key"]}

        snapshot = client.post(
            "/api/agent/cash-snapshot",
            json={
                "atm_id": "ATM-CASH-MISMATCH",
                "source": "xfs_cdm",
                "atm_cash_mode": "DISPENSE_ONLY",
                "read_at": "2026-05-25T11:00:00Z",
                "cash_units": [
                    {
                        "cassette_no": 1,
                        "cassette_id": "CST01",
                        "cassette_name": "Dispense Cassette 1",
                        "reported_currency": "EUR",
                        "reported_denomination": 50,
                        "initial_count": 2000,
                        "current_count": 900,
                        "reject_count": 0,
                        "retract_count": 0,
                        "dispensed_count": 1100,
                        "presented_count": 1100,
                        "status": "OK",
                        "physical_status": "PRESENT",
                    }
                ],
            },
            headers=agent_headers,
        )
        assert snapshot.status_code == 200

        details = client.get("/api/cash/atms/ATM-CASH-MISMATCH", headers=headers)
        assert details.status_code == 200
        unit = details.json()["units"][0]
        assert unit["reported_currency"] == "YER"
        assert unit["reported_denomination"] == 1000
        assert unit["expected_currency"] == "YER"
        assert unit["expected_denomination"] == 1000
        assert unit["layout_match_status"] == "MATCH"
        issue_codes = {issue["code"] for issue in details.json()["verification"]["issues"]}
        assert "CURRENCY_MISMATCH" not in issue_codes
        assert "DENOMINATION_MISMATCH" not in issue_codes


def test_cash_read_now_expires_stale_pending_command() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={
                "atm_id": "ATM-CASH-READ-NOW",
                "name": "Read Now ATM",
                "vpn_ip": "10.10.0.57",
                "branch": "HQ",
                "cash_monitoring_enabled": True,
            },
            headers=headers,
        )
        assert atm_response.status_code == 201

        first = client.post("/api/cash/atms/ATM-CASH-READ-NOW/read-now", headers=headers)
        assert first.status_code == 202
        first_command_id = first.json()["id"]

        stale_created_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).replace(tzinfo=None)
        with sqlite3.connect(TEST_DB) as connection:
            connection.execute(
                "UPDATE agent_commands SET created_at = ? WHERE id = ?",
                (stale_created_at.isoformat(sep=" "), first_command_id),
            )

        second = client.post("/api/cash/atms/ATM-CASH-READ-NOW/read-now", headers=headers)
        assert second.status_code == 202
        assert second.json()["id"] != first_command_id
        assert second.json()["status"] == "pending"
        second_command_id = second.json()["id"]

        with sqlite3.connect(TEST_DB) as connection:
            old_status, old_error = connection.execute(
                "SELECT status, last_error FROM agent_commands WHERE id = ?",
                (first_command_id,),
            ).fetchone()
        assert old_status == "failed"
        assert "expired" in old_error

        details = client.get("/api/cash/atms/ATM-CASH-READ-NOW", headers=headers)
        assert details.status_code == 200
        assert details.json()["last_cash_read_command"]["id"] == second_command_id


def test_cash_snapshot_cannot_impersonate_other_atm() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm1 = client.post(
            "/api/atms",
            json={"atm_id": "ATM-CASH-1", "name": "Cash 1", "vpn_ip": "10.10.0.43", "branch": "HQ"},
            headers=headers,
        )
        atm2 = client.post(
            "/api/atms",
            json={"atm_id": "ATM-CASH-2", "name": "Cash 2", "vpn_ip": "10.10.0.44", "branch": "HQ"},
            headers=headers,
        )
        assert atm1.status_code == 201
        assert atm2.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-CASH-1", "X-API-Key": atm1.json()["api_key"]}

        response = client.post(
            "/api/agent/cash-snapshot",
            json={"atm_id": "ATM-CASH-2", "source": "xfs_cdm", "read_at": "2026-05-25T10:30:00Z", "cash_units": []},
            headers=agent_headers,
        )
        assert response.status_code == 403


def test_atm_settings_reject_paths_outside_managed_root() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-PATHS", "name": "Path ATM", "vpn_ip": "10.10.0.25", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201

        for path in ["C:/Windows/System32", "D:/ATM/Media", "../ATM/Media", "\\\\server\\share"]:
            response = client.put("/api/atms/ATM-PATHS", json={"media_path": path}, headers=headers)
            assert response.status_code == 422

        valid = client.put("/api/atms/ATM-PATHS", json={"media_path": "C:/ATM/Screens"}, headers=headers)
        assert valid.status_code == 200


def test_admin_can_delete_atm_and_agent_credentials_stop_working() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-DELETE", "name": "Delete ATM", "vpn_ip": "10.10.0.21", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-DELETE", "X-API-Key": atm_response.json()["api_key"]}

        before_delete = client.post("/api/agent/heartbeat", json={"atm_id": "ATM-DELETE"}, headers=agent_headers)
        assert before_delete.status_code == 200

        deleted = client.delete("/api/atms/ATM-DELETE", headers=headers)
        assert deleted.status_code == 204

        after_delete = client.get("/api/atms/ATM-DELETE", headers=headers)
        assert after_delete.status_code == 404

        heartbeat = client.post("/api/agent/heartbeat", json={"atm_id": "ATM-DELETE"}, headers=agent_headers)
        assert heartbeat.status_code == 401

        audits = client.get("/api/logs/audit?limit=20", headers=headers)
        assert audits.status_code == 200
        assert any(item["action"] == "atm_deleted" and item["entity_id"] == "ATM-DELETE" for item in audits.json())


def test_delete_atm_with_active_update_requires_force() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-ACTIVE", "name": "Active ATM", "vpn_ip": "10.10.0.23", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201

        upload = client.post(
            "/api/packages/upload",
            data={"version": "delete-active-package"},
            files={"file": ("active.zip", make_zip({"welcome.png": b"fake"}), "application/zip")},
            headers=headers,
        )
        assert upload.status_code == 201
        package = upload.json()

        assign = client.post(f"/api/packages/{package['id']}/assign", json={"atm_ids": ["ATM-ACTIVE"]}, headers=headers)
        assert assign.status_code == 200

        blocked = client.delete("/api/atms/ATM-ACTIVE", headers=headers)
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["active_update_count"] == 1

        forced = client.delete("/api/atms/ATM-ACTIVE?force=true", headers=headers)
        assert forced.status_code == 204


def test_remote_atm_commands_are_disabled_for_unified_agent() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-REBOOT", "name": "Reboot ATM", "vpn_ip": "10.10.0.27", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-REBOOT", "X-API-Key": atm_response.json()["api_key"]}

        request = client.post(
            "/api/atms/ATM-REBOOT/reboot",
            json={"confirmation": "REBOOT", "reason": "maintenance", "delay_seconds": 60},
            headers=headers,
        )
        assert request.status_code == 410

        actions = client.get("/api/agent/commands", headers=agent_headers)
        assert actions.status_code == 200
        assert actions.json() == []


def test_reboot_endpoint_stays_disabled_even_with_active_update() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-REBOOT-ACTIVE", "name": "Active Reboot", "vpn_ip": "10.10.0.28", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201
        upload = client.post(
            "/api/packages/upload",
            data={"version": "reboot-active-package"},
            files={"file": ("reboot.zip", make_zip({"welcome.png": b"fake"}), "application/zip")},
            headers=headers,
        )
        assert upload.status_code == 201
        package = upload.json()
        assign = client.post(
            f"/api/packages/{package['id']}/assign",
            json={"atm_ids": ["ATM-REBOOT-ACTIVE"]},
            headers=headers,
        )
        assert assign.status_code == 200

        blocked = client.post(
            "/api/atms/ATM-REBOOT-ACTIVE/reboot",
            json={"confirmation": "REBOOT", "delay_seconds": 60},
            headers=headers,
        )
        assert blocked.status_code == 410

        forced = client.post(
            "/api/atms/ATM-REBOOT-ACTIVE/reboot?force=true",
            json={"confirmation": "REBOOT", "delay_seconds": 60},
            headers=headers,
        )
        assert forced.status_code == 410


def test_retry_failed_package_targets() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-RETRY", "name": "Retry ATM", "vpn_ip": "10.10.0.26", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-RETRY", "X-API-Key": atm_response.json()["api_key"]}

        upload = client.post(
            "/api/packages/upload",
            data={"version": "retry-failed-package"},
            files={"file": ("retry.zip", make_zip({"welcome.png": b"fake"}), "application/zip")},
            headers=headers,
        )
        assert upload.status_code == 201
        package = upload.json()

        assign = client.post(f"/api/packages/{package['id']}/assign", json={"atm_ids": ["ATM-RETRY"]}, headers=headers)
        assert assign.status_code == 200

        failed = client.post(
            "/api/agent/report-result",
            json={"package_id": package["id"], "status": "failed", "message": "copy failed"},
            headers=agent_headers,
        )
        assert failed.status_code == 200

        retry = client.post(f"/api/packages/{package['id']}/retry-failed", headers=headers)
        assert retry.status_code == 200
        assert retry.json()["assigned"] == 1
        assert retry.json()["targets"][0]["status"] == "pending"

        details = client.get(f"/api/packages/{package['id']}", headers=headers)
        assert details.status_code == 200
        assert details.json()["targets"][0]["last_error"] is None


def test_admin_can_regenerate_atm_api_key() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-KEY", "name": "Key ATM", "vpn_ip": "10.10.0.22", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201
        old_key = atm_response.json()["api_key"]
        old_agent_headers = {"X-ATM-ID": "ATM-KEY", "X-API-Key": old_key}

        before = client.get("/api/agent/config", headers=old_agent_headers)
        assert before.status_code == 200

        regenerated = client.post("/api/atms/ATM-KEY/regenerate-api-key", headers=headers)
        assert regenerated.status_code == 200
        new_key = regenerated.json()["api_key"]
        assert new_key != old_key

        old_after = client.get("/api/agent/config", headers=old_agent_headers)
        assert old_after.status_code == 401

        new_after = client.get("/api/agent/config", headers={"X-ATM-ID": "ATM-KEY", "X-API-Key": new_key})
        assert new_after.status_code == 200

        audits = client.get("/api/logs/audit?limit=20", headers=headers)
        assert audits.status_code == 200
        assert any(
            item["action"] == "atm_api_key_regenerated" and item["entity_id"] == "ATM-KEY"
            for item in audits.json()
        )


def test_atm_read_includes_last_agent_error() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_response = client.post(
            "/api/atms",
            json={"atm_id": "ATM-ERROR", "name": "Error ATM", "vpn_ip": "10.10.0.24", "branch": "HQ"},
            headers=headers,
        )
        assert atm_response.status_code == 201
        agent_headers = {"X-ATM-ID": "ATM-ERROR", "X-API-Key": atm_response.json()["api_key"]}

        log = client.post(
            "/api/agent/logs",
            json={"atm_id": "ATM-ERROR", "level": "error", "message": "Copy failed"},
            headers=agent_headers,
        )
        assert log.status_code == 200

        atm = client.get("/api/atms/ATM-ERROR", headers=headers)
        assert atm.status_code == 200
        assert atm.json()["last_agent_error"] == "Copy failed"


def test_upload_rejects_path_traversal() -> None:
    with TestClient(app) as client:
        headers = login(client)
        zip_buffer = make_zip({"../evil.png": b"not allowed"})
        response = client.post(
            "/api/packages/upload",
            files={"file": ("evil.zip", zip_buffer, "application/zip")},
            headers=headers,
        )
        assert response.status_code == 400


def test_upload_rejects_scripts_and_executables() -> None:
    with TestClient(app) as client:
        headers = login(client)
        for filename in ["bad.ps1", "bad.exe"]:
            zip_buffer = make_zip({filename: b"not allowed"})
            response = client.post(
                "/api/packages/upload",
                data={"version": f"reject-{filename}"},
                files={"file": ("bad.zip", zip_buffer, "application/zip")},
                headers=headers,
            )
            assert response.status_code == 400


def test_agent_cannot_download_unassigned_package_and_check_update_is_targeted() -> None:
    with TestClient(app) as client:
        headers = login(client)
        atm_a = client.post(
            "/api/atms",
            json={"atm_id": "ATM-TARGET-A", "name": "Target A", "vpn_ip": "10.10.0.31", "branch": "HQ"},
            headers=headers,
        )
        atm_b = client.post(
            "/api/atms",
            json={"atm_id": "ATM-TARGET-B", "name": "Target B", "vpn_ip": "10.10.0.32", "branch": "HQ"},
            headers=headers,
        )
        assert atm_a.status_code == 201
        assert atm_b.status_code == 201
        headers_a = {"X-ATM-ID": "ATM-TARGET-A", "X-API-Key": atm_a.json()["api_key"]}
        headers_b = {"X-ATM-ID": "ATM-TARGET-B", "X-API-Key": atm_b.json()["api_key"]}

        upload = client.post(
            "/api/packages/upload",
            data={"version": "targeted-package"},
            files={"file": ("targeted.zip", make_zip({"welcome.png": b"fake"}), "application/zip")},
            headers=headers,
        )
        assert upload.status_code == 201
        package = upload.json()

        assign = client.post(f"/api/packages/{package['id']}/assign", json={"atm_ids": ["ATM-TARGET-A"]}, headers=headers)
        assert assign.status_code == 200

        check_a = client.get("/api/agent/check-update", headers=headers_a)
        check_b = client.get("/api/agent/check-update", headers=headers_b)
        assert check_a.status_code == 200
        assert check_a.json()["has_update"] is True
        assert check_b.status_code == 200
        assert check_b.json()["has_update"] is False

        denied = client.get(f"/api/agent/download/{package['id']}", headers=headers_b)
        assert denied.status_code == 404


def test_upload_ignores_macos_zip_metadata() -> None:
    with TestClient(app) as client:
        headers = login(client)
        zip_buffer = make_zip(
            {
                "screens/welcome.png": b"fake-png-bytes",
                "__MACOSX/._screens": b"apple folder metadata",
                "__MACOSX/screens/._welcome.png": b"apple metadata",
                "__MACOSX/screens/._G05.PCX": b"apple metadata",
                ".DS_Store": b"finder metadata",
            }
        )
        response = client.post(
            "/api/packages/upload",
            data={"version": "media-macos-metadata"},
            files={"file": ("macos.zip", zip_buffer, "application/zip")},
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["version"] == "media-macos-metadata"


def test_upload_rejects_pcx_media_files() -> None:
    with TestClient(app) as client:
        headers = login(client)
        zip_buffer = make_zip(
            {
                "640X480/G00.PCX": b"fake-pcx-bytes",
                "800x600/C00.bmp": b"fake-bmp-bytes",
                "1024X768/C00.jpg": b"fake-jpg-bytes",
            }
        )
        response = client.post(
            "/api/packages/upload",
            data={"version": "media-pcx-package"},
            files={"file": ("pcx.zip", zip_buffer, "application/zip")},
            headers=headers,
        )
        assert response.status_code == 400
