import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage

from sqlalchemy.orm import Session

from ..models import ATM, AtmCashAlert, NotificationDelivery, NotificationRecipient, NotificationSettings

ALERT_LABELS = {
    "CASH_LOW": "انخفاض النقد",
    "CASH_CRITICAL": "انخفاض النقد بشكل حرج",
    "CASH_EMPTY": "انتهاء النقد",
}


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


def build_cash_alert_email(atm: ATM, alert: AtmCashAlert) -> tuple[str, str]:
    label = ALERT_LABELS.get(alert.alert_type, alert.alert_type)
    subject = f"QIB ATM Manager - {label} - {atm.name} ({atm.atm_id})"
    body = "\n".join(
        [
            "QIB ATM Manager",
            "",
            f"نوع التنبيه: {label}",
            f"الصراف: {atm.name} ({atm.atm_id})",
            f"الفرع: {atm.branch}",
            f"الكاسيت: {alert.unit_no}",
            f"العدد الحالي: {alert.current_count}",
            f"حد التنبيه: {alert.threshold_count}",
            f"وقت الفتح: {alert.opened_at.isoformat()}",
            "",
            alert.message,
        ]
    )
    return subject, body


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


def send_email(settings: NotificationSettings, subject: str, body: str, recipient_email: str | None = None) -> None:
    recipient = recipient_email or settings.recipient_email
    if not settings.smtp_host or not settings.sender_email or not recipient:
        raise ValueError("Notification email settings are incomplete")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = settings.sender_email
    message["To"] = recipient
    message.set_content(body)

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
        send_email(settings, subject, body, recipient)
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

    subject, body = build_cash_alert_email(atm, alert)
    return create_email_delivery(
        db,
        settings,
        event_type=alert.alert_type,
        subject=subject,
        body=body,
        recipient_email=recipient_email,
        alert=alert,
        atm=atm,
    )


def send_test_notification(db: Session, settings: NotificationSettings) -> NotificationDelivery:
    subject = "QIB ATM Manager - Test notification"
    body = "\n".join(
        [
            "QIB ATM Manager",
            "",
            "هذه رسالة اختبار من مركز التنبيهات.",
            f"وقت الاختبار: {utcnow().isoformat()}",
        ]
    )
    if not settings.recipient_email:
        raise ValueError("Notification default recipient email is missing")
    return create_email_delivery(db, settings, event_type="TEST", subject=subject, body=body)
