import smtplib
import ssl
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape

from sqlalchemy.orm import Session

from ..models import ATM, AtmCashAlert, NotificationDelivery, NotificationRecipient, NotificationSettings

ALERT_LABELS = {
    "CASH_LOW": "انخفاض النقد",
    "CASH_CRITICAL": "انخفاض النقد بشكل حرج",
    "CASH_EMPTY": "انتهاء النقد",
}
BRAND_NAME = "QIB ATM Manager"
YEMEN_TIMEZONE = timezone(timedelta(hours=3))


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def get_notification_settings(db: Session) -> NotificationSettings:
    settings = db.query(NotificationSettings).order_by(NotificationSettings.id.asc()).first()
    if settings is None:
        settings = NotificationSettings()
        db.add(settings)
        db.flush()
    return settings


def alert_notification_enabled(settings: NotificationSettings, alert_type: str) -> bool:
    if alert_type in {"CASH_LOW", "CASH_CRITICAL"}:
        return settings.notify_cash_low
    if alert_type == "CASH_EMPTY":
        return settings.notify_cash_empty
    return False


def email_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    local_value = value.astimezone(YEMEN_TIMEZONE)
    period = "ص" if local_value.hour < 12 else "م"
    hour = local_value.hour % 12 or 12
    return f"{local_value.year}/{local_value.month}/{local_value.day} {period} {hour}:{local_value.minute:02d}:{local_value.second:02d} - توقيت اليمن"


def cash_alert_tone(alert_type: str) -> dict[str, str]:
    if alert_type == "CASH_EMPTY":
        return {"label": "حرج", "color": "#be123c", "bg": "#fff1f2", "border": "#fecdd3"}
    if alert_type == "CASH_CRITICAL":
        return {"label": "حرج", "color": "#be123c", "bg": "#fff1f2", "border": "#fecdd3"}
    return {"label": "تنبيه", "color": "#92400e", "bg": "#fffbeb", "border": "#fde68a"}


def value_direction(value: object) -> str:
    text = str(value)
    if "@" in text:
        return "ltr"
    if text.isascii() and any(char.isalpha() for char in text):
        return "ltr"
    return "rtl"


def detail_row(label: str, value: object) -> str:
    direction = value_direction(value)
    return f"""
      <tr>
        <td dir="rtl" align="right" style="padding:12px 0;color:#64748b;font-size:14px;border-bottom:1px solid #e2e8f0;text-align:right;direction:rtl;">{escape(label)}</td>
        <td dir="{direction}" align="right" style="padding:12px 0;color:#0f172a;font-size:15px;font-weight:700;border-bottom:1px solid #e2e8f0;text-align:right;direction:{direction};">{escape(str(value))}</td>
      </tr>
    """


def branded_email_html(
    *,
    title: str,
    subtitle: str,
    badge: str,
    tone: dict[str, str],
    rows: list[tuple[str, object]],
    note: str,
) -> str:
    details = "\n".join(detail_row(label, value) for label, value in rows)
    return f"""<!doctype html>
<html lang="ar" dir="rtl">
  <body dir="rtl" style="margin:0;background:#f3f6f8;color:#0f172a;font-family:Arial,Tahoma,sans-serif;direction:rtl;text-align:right;">
    <div style="display:none;max-height:0;overflow:hidden;opacity:0;">{escape(subtitle)}</div>
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" dir="rtl" style="background:#f3f6f8;direction:rtl;text-align:right;">
      <tr>
        <td align="center" style="padding:28px 14px;">
          <table role="presentation" width="640" cellspacing="0" cellpadding="0" dir="rtl" style="width:100%;max-width:640px;background:#ffffff;border:1px solid #dbe4ee;border-radius:14px;overflow:hidden;box-shadow:0 8px 24px rgba(15,23,42,0.08);direction:rtl;text-align:right;">
            <tr>
              <td dir="rtl" align="right" style="background:#0f766e;padding:24px 26px;color:#ffffff;text-align:right;direction:rtl;">
                <div style="font-size:13px;font-weight:700;letter-spacing:0;color:#ccfbf1;">{BRAND_NAME}</div>
                <div style="margin-top:8px;font-size:28px;line-height:1.35;font-weight:800;">{escape(title)}</div>
                <div style="margin-top:6px;font-size:14px;color:#d1fae5;">{escape(subtitle)}</div>
              </td>
            </tr>
            <tr>
              <td dir="rtl" align="right" style="padding:24px 26px;text-align:right;direction:rtl;">
                <div style="display:inline-block;background:{tone['bg']};color:{tone['color']};border:1px solid {tone['border']};border-radius:999px;padding:7px 13px;font-size:13px;font-weight:800;">
                  {escape(badge)}
                </div>
                <table role="presentation" width="100%" cellspacing="0" cellpadding="0" dir="rtl" style="margin-top:18px;border-collapse:collapse;direction:rtl;text-align:right;">
                  {details}
                </table>
                <div dir="rtl" style="margin-top:20px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px 16px;color:#334155;font-size:14px;line-height:1.8;text-align:right;direction:rtl;">
                  {escape(note)}
                </div>
              </td>
            </tr>
            <tr>
              <td style="background:#f8fafc;border-top:1px solid #e2e8f0;padding:14px 26px;color:#64748b;font-size:12px;text-align:center;">
                رسالة تلقائية من {BRAND_NAME}. يرجى عدم الرد على هذا البريد.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""


def build_cash_alert_email(atm: ATM, alert: AtmCashAlert) -> tuple[str, str, str]:
    label = ALERT_LABELS.get(alert.alert_type, alert.alert_type)
    tone = cash_alert_tone(alert.alert_type)
    subject = f"{BRAND_NAME} - {label} - {atm.name} ({atm.atm_id})"
    body = "\n".join(
        [
            BRAND_NAME,
            "",
            f"نوع التنبيه: {label}",
            f"الصراف: {atm.name} ({atm.atm_id})",
            f"الفرع: {atm.branch}",
            f"الكاسيت: {alert.unit_no}",
            f"العدد الحالي: {alert.current_count}",
            f"حد التنبيه: {alert.threshold_count}",
            f"وقت الفتح: {email_datetime(alert.opened_at)}",
            "",
            alert.message,
        ]
    )
    html_body = branded_email_html(
        title=label,
        subtitle=f"{atm.name} - {atm.atm_id}",
        badge=tone["label"],
        tone=tone,
        rows=[
            ("الصراف", f"{atm.name} ({atm.atm_id})"),
            ("الفرع", atm.branch),
            ("الكاسيت", alert.unit_no),
            ("العدد الحالي", alert.current_count),
            ("حد التنبيه", alert.threshold_count),
            ("وقت الفتح", email_datetime(alert.opened_at)),
        ],
        note=alert.message,
    )
    return subject, body, html_body


def build_switch_probe_failed_email(
    atm: ATM,
    host: str,
    port: int,
    error_message: str,
    failed_at: datetime,
) -> tuple[str, str, str]:
    tone = {"label": "خارج الخدمة", "color": "#be123c", "bg": "#fff1f2", "border": "#fecdd3"}
    title = "فشل اتصال السويتش"
    subject = f"{BRAND_NAME} - {title} - {atm.name} ({atm.atm_id})"
    target = f"{host}:{port}"
    body = "\n".join(
        [
            BRAND_NAME,
            "",
            f"نوع التنبيه: {title}",
            f"الصراف: {atm.name} ({atm.atm_id})",
            f"الفرع: {atm.branch}",
            f"هدف السويتش: {target}",
            f"وقت الفشل: {email_datetime(failed_at)}",
            "",
            error_message,
        ]
    )
    html_body = branded_email_html(
        title=title,
        subtitle=f"{atm.name} - {atm.atm_id}",
        badge=tone["label"],
        tone=tone,
        rows=[
            ("الصراف", f"{atm.name} ({atm.atm_id})"),
            ("الفرع", atm.branch),
            ("هدف السويتش", target),
            ("وقت الفشل", email_datetime(failed_at)),
        ],
        note=error_message,
    )
    return subject, body, html_body


def notification_recipient_for_atm(db: Session, settings: NotificationSettings, atm: ATM) -> str | None:
    recipient = (
        db.query(NotificationRecipient)
        .filter(NotificationRecipient.atm_id == atm.id)
        .first()
    )
    if recipient is not None:
        if not recipient.enabled:
            return None
        return recipient.recipient_email or settings.recipient_email
    return settings.recipient_email


def send_email(
    settings: NotificationSettings,
    subject: str,
    body: str,
    recipient_email: str | None = None,
    html_body: str | None = None,
) -> None:
    recipient = recipient_email or settings.recipient_email
    if not settings.smtp_host or not settings.sender_email or not recipient:
        raise ValueError("Notification email settings are incomplete")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.sender_email
    message["To"] = recipient
    message.set_content(body)
    if html_body:
        message.add_alternative(html_body, subtype="html")

    timeout_seconds = 10
    if settings.smtp_security == "ssl":
        with smtplib.SMTP_SSL(
            settings.smtp_host,
            settings.smtp_port,
            timeout=timeout_seconds,
            context=ssl.create_default_context(),
        ) as client:
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password or "")
            client.send_message(message)
        return

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout_seconds) as client:
        if settings.smtp_security == "starttls":
            client.starttls(context=ssl.create_default_context())
        if settings.smtp_username:
            client.login(settings.smtp_username, settings.smtp_password or "")
        client.send_message(message)


def create_email_delivery(
    db: Session,
    settings: NotificationSettings,
    *,
    event_type: str,
    subject: str,
    body: str,
    html_body: str | None = None,
    recipient_email: str | None = None,
    alert: AtmCashAlert | None = None,
    atm: ATM | None = None,
) -> NotificationDelivery:
    recipient = recipient_email or settings.recipient_email
    if not recipient:
        raise ValueError("Notification recipient email is missing")

    delivery = NotificationDelivery(
        alert_id=alert.id if alert else None,
        atm_id=atm.id if atm else None,
        event_type=event_type,
        recipient_email=recipient,
        subject=subject,
        status="pending",
    )
    db.add(delivery)
    db.flush()

    try:
        send_email(settings, subject, body, recipient, html_body)
    except Exception as exc:  # SMTP errors should not block cash snapshot ingestion.
        delivery.status = "failed"
        delivery.error_message = str(exc)[:1000]
        return delivery

    delivery.status = "sent"
    delivery.sent_at = utcnow()
    return delivery


def notify_cash_alert_opened(db: Session, atm: ATM, alert: AtmCashAlert) -> NotificationDelivery | None:
    existing_delivery = (
        db.query(NotificationDelivery)
        .filter(NotificationDelivery.alert_id == alert.id)
        .first()
        if alert.id
        else None
    )
    if existing_delivery is not None:
        return None

    settings = get_notification_settings(db)
    if not settings.enabled or not settings.is_configured:
        return None
    if not alert_notification_enabled(settings, alert.alert_type):
        return None
    recipient_email = notification_recipient_for_atm(db, settings, atm)
    if not recipient_email:
        return None

    subject, body, html_body = build_cash_alert_email(atm, alert)
    return create_email_delivery(
        db,
        settings,
        event_type=alert.alert_type,
        subject=subject,
        body=body,
        html_body=html_body,
        recipient_email=recipient_email,
        alert=alert,
        atm=atm,
    )


def notify_switch_probe_failed(
    db: Session,
    atm: ATM,
    host: str,
    port: int,
    error_message: str,
    failed_at: datetime,
) -> NotificationDelivery | None:
    settings = get_notification_settings(db)
    if not settings.enabled or not settings.is_configured:
        return None
    recipient_email = notification_recipient_for_atm(db, settings, atm)
    if not recipient_email:
        return None

    subject, body, html_body = build_switch_probe_failed_email(atm, host, port, error_message, failed_at)
    return create_email_delivery(
        db,
        settings,
        event_type="SWITCH_DISCONNECTED",
        subject=subject,
        body=body,
        html_body=html_body,
        recipient_email=recipient_email,
        atm=atm,
    )


def send_test_notification(db: Session, settings: NotificationSettings) -> NotificationDelivery:
    subject = f"{BRAND_NAME} - Test notification"
    now = utcnow()
    body = "\n".join(
        [
            BRAND_NAME,
            "",
            "هذه رسالة اختبار من مركز التنبيهات.",
            f"وقت الاختبار: {email_datetime(now)}",
        ]
    )
    html_body = branded_email_html(
        title="رسالة اختبار",
        subtitle="مركز التنبيهات يعمل",
        badge="اختبار",
        tone={"label": "اختبار", "color": "#0f766e", "bg": "#ecfdf5", "border": "#99f6e4"},
        rows=[
            ("الحالة", "SMTP جاهز"),
            ("وقت الاختبار", email_datetime(now)),
            ("المستلم", settings.recipient_email or "-"),
        ],
        note="هذه رسالة اختبار من مركز التنبيهات للتأكد من إعدادات SMTP وهوية البريد.",
    )
    if not settings.recipient_email:
        raise ValueError("Notification default recipient email is missing")
    return create_email_delivery(db, settings, event_type="TEST", subject=subject, body=body, html_body=html_body)
