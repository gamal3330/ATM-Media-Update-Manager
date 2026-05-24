# ATM Media Update Manager

MVP لإدارة تحديث ملفات الصور على صرافات Windows عبر نموذج Pull آمن. السيرفر لا يدخل إلى الصرافات ولا يفتح جلسات عليها؛ كل صراف يشغل Agent يسأل السيرفر عن التحديثات عندما يكون متصلاً عبر VPN.

## المكونات

- `backend/`: FastAPI + SQLite + SQLAlchemy.
- `frontend/`: React + Tailwind Dashboard.
- `agent/`: Agent دائم قابل للبناء كملف `atm-agent.exe` ويعمل كـ Windows Service.

## التشغيل المحلي

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
  "fallback_check_interval_seconds": 300,
  "fallback_heartbeat_interval_seconds": 60
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
ATM Media Update Agent
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
5. عندما يتصل الـ Agent، يرسل heartbeat ثم يتحقق من وجود تحديث.
6. عند وجود تحديث، يرسل الـ Agent تقدم العملية للسيرفر: تنزيل ZIP، التحقق من SHA256، فك الضغط، Backup، ونسخ الملفات.
7. إذا كان ZIP يحتوي مجلداً رئيسياً واحداً فقط، ينسخ الـ Agent محتوياته مباشرة داخل `media_path`. المجلدات الداخلية المهمة مثل مجلدات المقاسات تبقى كما هي.
8. في حال الفشل، يحاول Rollback من آخر Backup ويرسل سبب الفشل للسيرفر.
9. من صفحة تفاصيل التحديثات استخدم `Retry Failed` لإعادة محاولة الصرافات الفاشلة فقط.

## تشغيل الصراف عملياً

1. من لوحة التحكم أضف الصراف واحفظ `API Key`.
2. افتح صفحة `Agent Downloads` وحمّل `ATM-Agent-Build-Source.zip`.
3. على جهاز بناء Windows:

```powershell
Expand-Archive .\ATM-Agent-Build-Source.zip -DestinationPath .\ATM-Agent
cd .\ATM-Agent
.\build_agent.bat
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

6. على الصراف افتح Command Prompt أو PowerShell كمسؤول وشغّل أمر التثبيت المنسوخ من لوحة التحكم:

```bat
atm-agent.exe install --server-url http://SERVER:8001 --atm-id ATM001 --api-key "KEY"
```

7. للتحقق:

```bat
atm-agent.exe status
sc.exe query ATMMediaAgent
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

## إعادة تشغيل الصراف

- من صفحة الصرافات يوجد زر `Restart ATM`.
- العملية لا تتم بدخول مباشر من السيرفر إلى الصراف؛ يتم تسجيل طلب ثابت، والـ Agent يسحبه بنظام Pull.
- يظهر تحذير قبل إنشاء الطلب، وتحذير إضافي إذا كان على الصراف تحديث نشط.
- الطلب يسجل في `audit_logs` باسم `atm_reboot_requested`.
- الـ Agent ينفذ إعادة تشغيل Windows بمهلة افتراضية 60 ثانية عبر إجراء ثابت فقط، وليس عبر أوامر Shell عامة.

## ملاحظات أمنية مهمة

- لا يتم تنفيذ أي EXE أو Script من داخل حزمة ZIP على الصراف؛ الحزمة مخصصة لملفات الصور فقط.
- الامتدادات المسموحة داخل ZIP فقط: `jpg`, `jpeg`, `png`, `bmp`, `gif`, `pcx`.
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
