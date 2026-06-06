# QIB ATM Manager WhatsApp Gateway

Standalone WhatsApp Web gateway used by QIB ATM Manager notification center.

## Install

```powershell
cd C:\Project\ATM-Media-Update-Manager\whatsapp-gateway
npm install
```

## Run

```powershell
.\start-whatsapp-gateway.ps1 -Port 3020
```

Optional shared token:

```powershell
.\start-whatsapp-gateway.ps1 -Port 3020 -Token "change-this-token"
```

Then open QIB ATM Manager, go to Notification Center, configure:

- Gateway URL: `http://127.0.0.1:3020`
- Gateway Token: the same token, if used
- Default WhatsApp recipient: phone number with country code, for example `9677XXXXXXX`

Scan the QR code from the Notification Center. The session is stored under `.wwebjs_auth`.

The gateway automatically schedules reconnect attempts if WhatsApp Web disconnects. The current status includes
`reconnect_attempts`, `last_disconnected_at`, and `next_reconnect_at`.

Per-ATM WhatsApp recipients can contain more than one number. In QIB ATM Manager, separate numbers with commas, for example:

```text
9677XXXXXXX, 9677YYYYYYY
```

## Endpoints

- `GET /health`
- `GET /status`
- `GET /qr`
- `POST /send` with JSON body `{ "to": "9677XXXXXXX", "message": "text" }`
