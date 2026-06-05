# QIB ATM Manager Android

تطبيق Android خفيف يفتح نظام `QIB ATM Manager` داخل WebView.

الرابط الافتراضي:

```text
http://172.16.23.34:8001
```

## تغيير رابط السيرفر

عدّل القيمة في:

```text
android-app/app/build.gradle
```

```gradle
buildConfigField "String", "SERVER_URL", "\"http://172.16.23.34:8001\""
```

## البناء عبر Android Studio

1. افتح Android Studio.
2. اختر `File > Open`.
3. افتح مجلد `android-app`.
4. انتظر Gradle Sync.
5. اختر `Build > Build Bundle(s) / APK(s) > Build APK(s)`.

سيظهر ملف APK غالبا في:

```text
android-app/app/build/outputs/apk/debug/app-debug.apk
```

## البناء عبر الأوامر

إذا كان Android SDK وGradle وJDK 17+ مثبتين:

```powershell
cd android-app
gradle :app:assembleDebug
```

أو استخدم سكربت التحقق:

```powershell
.\build-apk.ps1
```

السكربت يحاول تلقائيا:

- استخدام JBR المرفق مع Android Studio.
- ضبط `ANDROID_HOME` على SDK الافتراضي.
- تنزيل Gradle محليا داخل `.gradle/bootstrap` إذا لم يكن Gradle موجودا في PATH.

## ملاحظات

- التطبيق يحتاج اتصالا بالشبكة الداخلية أو VPN للوصول إلى `172.16.23.34`.
- تم السماح بـ HTTP لأن النظام يعمل حاليا على `http://`.
- عند الانتقال إلى HTTPS لاحقا يفضل إزالة `usesCleartextTraffic`.
- Android Studio يحتوي عادة على JDK مناسب للبناء. Java 8 وحده لا يكفي لبناء هذا المشروع، لذلك يستخدم السكربت JBR الخاص بـ Android Studio عند وجوده.
