from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..auth import get_current_user
from ..database import get_db
from ..models import ATM, NotificationDelivery, NotificationRecipient, NotificationSettings, User
from ..page_permissions import SYSTEM_ADMIN_ROLES
from ..schemas import (
    NotificationDeliveryRead,
    NotificationRetryResult,
    NotificationRecipientRead,
    NotificationRecipientsUpdate,
    NotificationSettingsRead,
    NotificationSettingsUpdate,
)
from ..services.audit_service import write_audit
from ..services.notification_service import (
    get_notification_settings,
    get_whatsapp_gateway_qr,
    retry_failed_notification_deliveries,
    send_test_notification,
    send_test_whatsapp_notification,
    sync_whatsapp_gateway_status,
)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


def unique_values(values: list[str | None]) -> list[str]:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result


def require_notification_manager(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role not in {*SYSTEM_ADMIN_ROLES, "cash_monitoring_admin"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


@router.get("/settings", response_model=NotificationSettingsRead)
def read_notification_settings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> NotificationSettings:
    return get_notification_settings(db)


@router.put("/settings", response_model=NotificationSettingsRead)
def update_notification_settings(
    payload: NotificationSettingsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> NotificationSettings:
    settings = get_notification_settings(db)
    changes = payload.model_dump(
        exclude={
            "enabled",
            "email_enabled",
            "smtp_password",
            "clear_smtp_password",
            "whatsapp_gateway_token",
            "clear_whatsapp_gateway_token",
            "whatsapp_default_recipients",
        }
    )
    for key, value in changes.items():
        setattr(settings, key, value)

    default_whatsapp_recipients = payload.whatsapp_default_recipients or (
        [payload.whatsapp_default_recipient] if payload.whatsapp_default_recipient else []
    )
    smtp_ready = bool(payload.sender_email and payload.smtp_host)
    email_enabled = payload.email_enabled
    if "email_enabled" not in payload.model_fields_set:
        email_enabled = bool(payload.enabled and smtp_ready)
    settings.email_enabled = email_enabled
    settings.whatsapp_enabled = payload.whatsapp_enabled
    settings.enabled = bool(email_enabled or payload.whatsapp_enabled)
    settings.whatsapp_default_recipients_json = default_whatsapp_recipients
    settings.whatsapp_default_recipient = default_whatsapp_recipients[0] if default_whatsapp_recipients else None

    if payload.clear_smtp_password:
        settings.smtp_password = None
    elif payload.smtp_password:
        settings.smtp_password = payload.smtp_password

    if payload.clear_whatsapp_gateway_token:
        settings.whatsapp_gateway_token = None
    elif payload.whatsapp_gateway_token:
        settings.whatsapp_gateway_token = payload.whatsapp_gateway_token

    settings.updated_by = current_user.username
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="notification_settings_updated",
        entity_type="notification_settings",
        entity_id=str(settings.id),
        details={
            key: value
            for key, value in changes.items()
            if key not in {
                "smtp_password",
                "clear_smtp_password",
                "whatsapp_gateway_token",
                "clear_whatsapp_gateway_token",
            }
        },
    )
    db.commit()
    db.refresh(settings)
    return settings


def recipient_read(
    atm: ATM,
    recipient: NotificationRecipient | None,
    default_email: str | None,
    default_whatsapp_numbers: list[str],
) -> NotificationRecipientRead:
    enabled = recipient.enabled if recipient else True
    custom_email = recipient.recipient_email if recipient else None
    custom_whatsapp_numbers = list(recipient.whatsapp_numbers_json or []) if recipient else []
    if not custom_whatsapp_numbers and recipient and recipient.whatsapp_number:
        custom_whatsapp_numbers = [recipient.whatsapp_number]
    custom_whatsapp = custom_whatsapp_numbers[0] if custom_whatsapp_numbers else recipient.whatsapp_number if recipient else None
    custom_whatsapp_numbers = [custom_whatsapp] if custom_whatsapp else []
    effective_email = (custom_email or default_email) if enabled else None
    effective_whatsapp_numbers = unique_values([*default_whatsapp_numbers, *custom_whatsapp_numbers]) if enabled else []
    effective_whatsapp = effective_whatsapp_numbers[0] if effective_whatsapp_numbers else None
    return NotificationRecipientRead(
        atm_id=atm.atm_id,
        name=atm.name,
        branch=atm.branch,
        recipient_email=custom_email,
        effective_recipient_email=effective_email,
        whatsapp_number=custom_whatsapp,
        whatsapp_numbers=custom_whatsapp_numbers,
        effective_whatsapp_number=effective_whatsapp,
        effective_whatsapp_numbers=effective_whatsapp_numbers if enabled else [],
        enabled=enabled,
        uses_default=enabled and not custom_email,
        updated_at=recipient.updated_at if recipient else None,
    )


@router.get("/recipients", response_model=list[NotificationRecipientRead])
def list_notification_recipients(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> list[NotificationRecipientRead]:
    settings = get_notification_settings(db)
    recipients = {item.atm_id: item for item in db.query(NotificationRecipient).all()}
    atms = db.query(ATM).order_by(ATM.branch.asc(), ATM.atm_id.asc()).all()
    return [
        recipient_read(atm, recipients.get(atm.id), settings.recipient_email, settings.whatsapp_default_recipients)
        for atm in atms
    ]


@router.put("/recipients", response_model=list[NotificationRecipientRead])
def update_notification_recipients(
    payload: NotificationRecipientsUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> list[NotificationRecipientRead]:
    atms_by_atm_id = {atm.atm_id: atm for atm in db.query(ATM).all()}
    existing = {item.atm_id: item for item in db.query(NotificationRecipient).all()}
    missing = [item.atm_id for item in payload.recipients if item.atm_id not in atms_by_atm_id]
    if missing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"missing_atm_ids": missing},
        )

    changed = []
    for item in payload.recipients:
        atm = atms_by_atm_id[item.atm_id]
        recipient = existing.get(atm.id)
        whatsapp_numbers = item.whatsapp_numbers or ([item.whatsapp_number] if item.whatsapp_number else [])
        whatsapp_number = whatsapp_numbers[0] if whatsapp_numbers else None
        whatsapp_numbers = [whatsapp_number] if whatsapp_number else []
        needs_row = bool(item.recipient_email) or bool(whatsapp_numbers) or not item.enabled
        if recipient is None and not needs_row:
            continue
        if recipient is None:
            recipient = NotificationRecipient(atm_id=atm.id)
            db.add(recipient)
            existing[atm.id] = recipient

        recipient.recipient_email = item.recipient_email
        recipient.whatsapp_numbers_json = whatsapp_numbers
        recipient.whatsapp_number = whatsapp_number
        recipient.enabled = item.enabled
        recipient.updated_by = current_user.username
        changed.append(
            {
                "atm_id": atm.atm_id,
                "recipient_email": item.recipient_email,
                "whatsapp_numbers": whatsapp_numbers,
                "enabled": item.enabled,
            }
        )

    if changed:
        write_audit(
            db,
            actor_type="user",
            actor_id=current_user.username,
            action="notification_recipients_updated",
            entity_type="notification_recipients",
            details={"count": len(changed), "recipients": changed},
        )
    db.commit()
    return list_notification_recipients(db=db, current_user=current_user)


@router.post("/test", response_model=NotificationDeliveryRead)
def test_notification_email(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> NotificationDelivery:
    settings = get_notification_settings(db)
    if not settings.is_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notification email settings are incomplete",
        )
    if not settings.recipient_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notification default recipient email is missing",
        )
    delivery = send_test_notification(db, settings)
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="notification_test_email_requested",
        entity_type="notification_delivery",
        entity_id=str(delivery.id),
        details={"status": delivery.status, "recipient_email": delivery.recipient_email},
    )
    db.commit()
    db.refresh(delivery)
    return delivery


@router.get("/whatsapp/status")
def whatsapp_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> dict:
    settings = get_notification_settings(db)
    result = sync_whatsapp_gateway_status(db, settings)
    db.commit()
    return result


@router.get("/whatsapp/qr")
def whatsapp_qr(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> dict:
    settings = get_notification_settings(db)
    return get_whatsapp_gateway_qr(settings)


@router.post("/whatsapp/test", response_model=NotificationDeliveryRead)
def test_whatsapp_notification(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> NotificationDelivery:
    settings = get_notification_settings(db)
    if not settings.is_whatsapp_configured:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="WhatsApp gateway settings are incomplete",
        )
    if not settings.whatsapp_default_recipients:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Notification default WhatsApp recipient is missing",
        )
    delivery = send_test_whatsapp_notification(db, settings)
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="notification_whatsapp_test_requested",
        entity_type="notification_delivery",
        entity_id=str(delivery.id),
        details={"status": delivery.status, "recipient": delivery.recipient_email},
    )
    db.commit()
    db.refresh(delivery)
    return delivery


@router.get("/deliveries", response_model=list[NotificationDeliveryRead])
def list_notification_deliveries(
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> list[NotificationDelivery]:
    return (
        db.query(NotificationDelivery)
        .order_by(NotificationDelivery.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )


@router.post("/deliveries/retry-failed", response_model=NotificationRetryResult)
def retry_failed_deliveries(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_notification_manager),
) -> dict:
    result = retry_failed_notification_deliveries(db, force=True, limit=100)
    write_audit(
        db,
        actor_type="user",
        actor_id=current_user.username,
        action="notification_failed_deliveries_retried",
        entity_type="notification_delivery",
        details={
            "retried": result["retried"],
            "sent": result["sent"],
            "failed": result["failed"],
            "skipped": result["skipped"],
        },
    )
    db.commit()
    for delivery in result["deliveries"]:
        db.refresh(delivery)
    return result
