# ATM Media Update Manager

MVP لإدارة تحديث ملفات الصور على صرافات Windows عبر نموذج Pull آمن. السيرفر لا يدخل إلى الصرافات ولا يفتح جلسات عليها؛ كل صراف يشغل Agent يسأل السيرفر عن التحديثات عندما يكون متصلاً عبر VPN.

## المكونات

- `backend/`: FastAPI + SQLite + SQLAlchemy.
- `frontend/`: React + Tailwind Dashboard.
- `agent/`: ATM Unified Agent دائم قابل للبناء كملف `atm-agent.exe` ويعمل كـ Windows Service واحدة.

## التشغيل المحلي

### تشغيل Windows بأمر واحد

على السيرفر المركزي Windows، بعد ضبط ملف `.env`، يمكن تشغيل الـ Backend والـ Frontend معاً:

```powershell
cd C:\ATM-Media-Update-Manager
.\start_server.bat
```

الملف ينشئ بيئة Python عند الحاجة، يثبت متطلبات الـ Backend والـ Frontend، ينسخ `.env` إلى `frontend\.env`، ثم يفتح نافذتين:

- Backend: `http://localhost:8001/docs`
- Frontend: `http://localhost:5175`

يمكن تغيير المنافذ:

```powershell
.\start_server.bat -BackendPort 8001 -FrontendPort 5175
```

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export JWT_SECRET_KEY="local-dev-secret-change-me"
export ADMIN_USERNAME="admin"
export ADMIN_PASSWORD="admin123!"
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

يفتح الـ API على:

```text
http://localhost:8000
```

توثيق Swagger:

```text
http://localhost:8000/docs
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

افتح:

```text
http://localhost:5173
```

بيانات الدخول الافتراضية محلياً هي القيم الموجودة في متغيرات البيئة:

```text
admin / admin123!
```

غيّرها قبل أي استخدام فعلي.

### 3. Agent

أنشئ صرافاً من لوحة التحكم واحفظ الـ API Key الذي يظهر مرة واحدة. المسارات مثل `media_path` و`backup_path` و`temp_path` لا تحفظ محلياً على الصراف؛ يتم سحبها من لوحة التحكم عبر `/api/agent/config`.

ملف الإعداد المحلي على الصراف يحتوي بيانات الربط فقط:

```json
{
  "server_url": "https://atm-update-server.local",
  "atm_id": "ATM001",
  "api_key": "CHANGE_ME",
  "local_log_path": "C:\\ATM\\Agent\\logs",
  "fallback_heartbeat_interval_seconds": 60,
  "fallback_config_sync_interval_seconds": 120
}
```

لبناء ملف Agent واحد على Windows:

```bat
cd agent
build_agent.bat
```

الناتج:

```text
agent\dist\atm-agent.exe
```

تثبيت الخدمة مرة واحدة فقط كمسؤول:

```bat
atm-agent.exe install --server-url https://atm-update-server.local --atm-id ATM001 --api-key XXXXX
```

بعد التثبيت تعمل الخدمة تلقائياً مع Windows باسم:

```text
ATM Unified Agent Service
```

أوامر مفيدة:

```bat
atm-agent.exe uninstall
atm-agent.exe status
atm-agent.exe run --config "C:\Program Files\ATM Media Agent\config.json" --once
```

تفاصيل أكثر في `agent/README.md`.

## Docker للـ Backend

```bash
docker compose up --build backend
```

## الاختبارات

```bash
cd backend
pytest
```

## تدفق العمل

1. أضف الصرافات واحفظ API Key لكل صراف في ملف إعدادات الـ Agent الخاص به.
2. من صفحة الصرافات يمكنك توليد `API Key` جديد ونسخ أمر التثبيت الجاهز.
3. ارفع ZIP يحتوي صوراً فقط.
4. عيّن الحزمة للصرافات المستهدفة.
5. عندما يتصل الـ Unified Agent، يرسل heartbeat ويسحب config الوحدات المفعلة.
6. Media Update Module يتحقق من وجود تحديث، ثم يرسل تقدم العملية للسيرفر: تنزيل ZIP، التحقق من SHA256، فك الضغط، Backup، ونسخ الملفات.
7. إذا كان ZIP يحتوي مجلداً رئيسياً واحداً فقط، ينسخ الـ Agent محتوياته مباشرة داخل `media_path`. المجلدات الداخلية المهمة مثل مجلدات المقاسات تبقى كما هي.
8. في حال الفشل، يحاول Rollback من آخر Backup ويرسل سبب الفشل للسيرفر.
9. Cash Monitoring Module مخصص لصرافات السحب فقط `DISPENSE_ONLY`، ويقرأ CDM dispense cassettes و reject/retract بنظام Read-Only عند تفعيله من لوحة التحكم.
10. من شاشة الصرافات يمكن طلب فحص الوصول إلى السويتش. الـ Agent ينفذ TCP connect فقط إلى `switch_probe_host:switch_probe_port`، بدون CMD وبدون `telnet.exe`.
11. من صفحة تفاصيل التحديثات استخدم `Retry Failed` لإعادة محاولة الصرافات الفاشلة فقط.

## تشغيل الصراف عملياً

1. من لوحة التحكم أضف الصراف واحفظ `API Key`.
2. افتح صفحة `Agent Downloads` وحمّل `ATM-Agent-Build-Source.zip`.
3. على جهاز بناء Windows، فك ضغط الملف ثم شغّل:

```bat
cd ATM-Agent
build_agent.bat
```

4. ضع الملف الناتج على السيرفر في:

```text
agent\dist\atm-agent.exe
```

بعد ذلك يمكن فتح صفحة `Agent Downloads` من داخل الصراف وتنزيل `atm-agent.exe` مباشرة.

5. أو انقل الملف الناتج إلى الصراف يدوياً:

```text
dist\atm-agent.exe
```

6. على الصراف افتح Command Prompt كمسؤول وشغّل أمر التثبيت المنسوخ من لوحة التحكم:

```bat
atm-agent.exe install --server-url http://SERVER:8001 --atm-id ATM001 --api-key "KEY"
```

7. للتحقق:

```bat
atm-agent.exe status
atm-agent.exe xfs-cdm-diagnose --aptra-root "C:\Program Files (x86)\NCR APTRA"
sc.exe query ATMUnifiedAgent
```

## إدارة المفاتيح

- لا يظهر `API Key` إلا عند إنشاء الصراف أو عند `Regenerate API Key`.
- عند توليد مفتاح جديد يتوقف المفتاح القديم فوراً.
- بعد تدوير المفتاح يجب تحديث الصراف أو إعادة تثبيت الخدمة بالأمر الجديد.
- كل عملية توليد مفتاح تسجل في `audit_logs`.

## متابعة الحزم

- شاشة التحديثات تعرض: مستهدف، ينتظر، جاري، تم، فشل.
- التقدم يحدث تلقائياً كل 3 ثوانٍ أثناء وجود صرافات في حالة `pending` أو `downloading`.
- زر `Retry Failed` يعيد الصرافات الفاشلة إلى `pending` فقط دون إعادة تعيين الناجحة.
- يمكن أيضاً اختيار صرافات فاشلة يدوياً وإعادة إرسال التعيين لها.

## ATM Unified Agent

- يوجد Agent واحد فقط وخدمة Windows واحدة باسم `ATM Unified Agent Service`.
- الكود الداخلي Modular ويحتوي حالياً على `media_update` و`cash_monitoring`.
- يمكن تفعيل أو تعطيل كل Module من إعدادات الصراف في لوحة التحكم.
- لا يستقبل الـ Agent أوامر Shell أو PowerShell أو PS1 من السيرفر.
- مسارات الصور والنسخ الاحتياطي وإعدادات مراقبة النقد تأتي من `/api/agent/config`.
- فحص السويتش ليس أمر Shell؛ هو TCP probe مقيّد على host/port المخزنين في إعدادات الصراف. القيمة الافتراضية: `172.16.25.75:10200`.
- كل الصرافات في هذه النسخة تعامل كصرافات سحب فقط `DISPENSE_ONLY`.
- Cash Monitoring يركز على `CDM = Cash Dispenser Module` فقط.
- الـ providers الحالية: `mock`, `xfs_cdm`, `vendor_cdm`.
- لا يوجد CIM أو Cash-In أو Deposit أو Recycler في هذه النسخة.

مثال إعدادات مراقبة النقد القادمة من السيرفر:

```json
{
  "cash_monitoring": {
    "enabled": true,
    "atm_cash_mode": "DISPENSE_ONLY",
    "provider": "xfs_cdm",
    "xfs_logical_service": "CDM",
    "read_interval_seconds": 120,
    "cash_layout": [
      { "cassette_no": 1, "currency": "YER", "denomination": 1000, "max_capacity": 2000, "low_threshold": 300, "critical_threshold": 100 },
      { "cassette_no": 2, "currency": "YER", "denomination": 1000, "max_capacity": 2000, "low_threshold": 300, "critical_threshold": 100 },
      { "cassette_no": 3, "currency": "USD", "denomination": 100, "max_capacity": 2000, "low_threshold": 100, "critical_threshold": 30 },
      { "cassette_no": 4, "currency": "SAR", "denomination": 100, "max_capacity": 2000, "low_threshold": 100, "critical_threshold": 30 }
    ],
    "stale_after_minutes": 10
  }
}
```

استخدم `MediaDispenser1` غالبًا لصرافات NCR APTRA، واستخدم `CDM` لصراف GRG الذي نجح معه أمر القراءة:

```powershell
.\atm-agent.exe xfs-cdm-read --logical-service "CDM" --msxfs-path "C:\Windows\SysWOW64\msxfs.dll" --json
```

## ملاحظات أمنية مهمة

- لا يتم تنفيذ أي EXE أو Script من داخل حزمة ZIP على الصراف؛ الحزمة مخصصة لملفات الصور فقط.
- الامتدادات المسموحة داخل ZIP فقط: `jpg`, `jpeg`, `png`, `bmp`, `gif`.
- Cash Monitoring Read-Only فقط: لا تنفيذ Dispense commands، لا Cash Unit Exchange، لا Reset Counters، ولا أي أمر يغيّر حالة الصراف.
- لوحة مراقبة النقد تعرض فقط dispense cassettes و available cash و reject/retract والتنبيهات الخاصة بها.
- لا تفعّل `xfs_cdm` على صراف حقيقي قبل تشغيل `atm-agent.exe xfs-cdm-diagnose` ومعرفة اسم CDM logical service الصحيح.
- فحص السويتش لا يستخدم `telnet` ولا CMD ولا PowerShell. إذا كان السويتش لا يقبل الاتصال على المنفذ المحدد، تظهر النتيجة Failed مع سبب الخطأ.
- يتم منع Path Traversal عند رفع ZIP في السيرفر وعند فكه في الـ Agent.
- يتم حفظ SHA256 لكل حزمة والتحقق منه قبل التطبيق.
- كلمات المرور لا تخزن كنص صريح؛ يتم استخدام PBKDF2-HMAC-SHA256.
- لوحة التحكم تستخدم JWT.
- كل صراف يستخدم API Key مستقل، ويخزن السيرفر hash للمفتاح لا المفتاح نفسه.
- مسارات `media_path`, `backup_path`, `temp_path` يجب أن تكون تحت `C:\ATM\...`.
- `backup_path` يجب ألا يكون داخل `media_path`.
- الوضع الافتراضي للـ Agent هو `replace_all`: يستبدل محتوى مسار الصور بالكامل بمحتوى ZIP الآمن.
- صلاحيات Administrator مطلوبة فقط إن قررت تثبيت الـ Agent كخدمة Windows.

## المرحلة التالية المقترحة

- إضافة صفحة مستخدمين وصلاحيات.
- إضافة PostgreSQL migration عبر Alembic.
- إضافة TLS خلف reverse proxy.
- إضافة retention policy للـ backups والـ logs.
