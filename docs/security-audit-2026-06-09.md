# Security Audit - 2026-06-09

## Scope

- Backend FastAPI authentication, authorization, upload, update, notification, cash, logs, and agent APIs.
- Frontend API error handling and session behavior surfaces.
- Windows Agent dependencies and packaged executables.
- WhatsApp gateway authentication boundary.
- Android client storage and cleartext transport configuration review.

## Remediated Findings

1. Server-side page authorization was incomplete.
   - Several APIs depended only on an authenticated user. A user without the matching page could still call APIs directly.
   - Added reusable page guards and applied them to packages, agent updates, downloads, logs, ATMs, cash monitoring, and notifications.

2. Unsafe production defaults were accepted.
   - Default JWT/admin secrets could be used if environment variables were missing.
   - Startup now rejects placeholder JWT secret, default admin password, and wildcard CORS with credentials unless `ALLOW_INSECURE_DEFAULTS=1`.

3. Login brute-force protection was missing.
   - Added per-username and client-IP throttling after repeated failures.

4. Known vulnerable dependencies were present.
   - Upgraded backend upload/API dependencies and agent `requests`.
   - Rebuilt `atm-agent.exe` and `agent-updater.exe` as 32-bit binaries.

5. WhatsApp gateway could be exposed without a token.
   - Gateway now requires `WHATSAPP_GATEWAY_TOKEN` when listening outside localhost.

6. Browser security headers were missing.
   - Added nosniff, frame denial, referrer policy, permissions policy, and HTTPS-only HSTS.

## Residual Risks

1. Web token storage still uses `localStorage`.
   - Recommended next step: migrate to HttpOnly secure cookies with SameSite protection.

2. Android token storage uses SharedPreferences.
   - Recommended next step: use Android EncryptedSharedPreferences.

3. Internal HTTP is still allowed for the Android app to the LAN API address.
   - Recommended next step: issue an internal TLS certificate and move API access to HTTPS.

4. SMTP and WhatsApp secrets are stored in application configuration.
   - Recommended next step: encrypt secrets at rest with a server-side master key or Windows DPAPI.

## Verification

- `python -m pytest backend\tests`
- `python -m pip_audit -r backend\requirements.txt`
- `python -m pip_audit -r agent\requirements.txt`
- `npm audit --omit=dev` in `frontend`
- `npm audit --omit=dev` in `whatsapp-gateway`
- `npm run build` in `frontend`
- `cmd /c agent\build_agent_x86.bat`

