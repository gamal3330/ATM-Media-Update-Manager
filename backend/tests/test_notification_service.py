import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.models import ATM, AtmCashAlert  # noqa: E402
from app.services.notification_service import build_cash_alert_email  # noqa: E402


def test_cash_alert_email_has_branded_html_and_plain_text() -> None:
    atm = ATM(atm_id="205", name="شحن", vpn_ip="192.168.35.205", branch="Sana'a")
    alert = AtmCashAlert(
        atm_id=1,
        unit_no=3,
        alert_type="CASH_LOW",
        severity="warning",
        message="CASH_LOW on dispense cassette 3: 80 notes",
        current_count=80,
        threshold_count=100,
        opened_at=datetime(2026, 6, 5, 14, 12, 0, tzinfo=timezone.utc),
    )

    subject, body, html_body = build_cash_alert_email(atm, alert)

    assert "QIB ATM Manager" in subject
    assert "انخفاض النقد" in subject
    assert "QIB ATM Manager" in body
    assert "العدد الحالي: 80" in body
    assert "<html" in html_body
    assert 'dir="rtl"' in html_body
    assert 'align="right"' in html_body
    assert "direction:rtl" in html_body
    assert "background:#0f766e" in html_body
    assert "CASH_LOW on dispense cassette 3" in html_body
