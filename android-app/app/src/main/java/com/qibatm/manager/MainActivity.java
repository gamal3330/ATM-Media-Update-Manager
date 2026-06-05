package com.qibatm.manager;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.Context;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.text.InputType;
import android.text.TextUtils;
import android.view.Gravity;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URLEncoder;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class MainActivity extends Activity {
    private static final String PREFS_NAME = "qib_atm_manager";
    private static final String PREF_TOKEN = "access_token";
    private static final String PREF_USERNAME = "username";
    private static final String PREF_SERVER_URL = "server_url";

    private static final int COLOR_BG = Color.rgb(244, 247, 251);
    private static final int COLOR_CARD = Color.WHITE;
    private static final int COLOR_INK = Color.rgb(15, 23, 42);
    private static final int COLOR_MUTED = Color.rgb(100, 116, 139);
    private static final int COLOR_LINE = Color.rgb(221, 230, 240);
    private static final int COLOR_TEAL = Color.rgb(15, 118, 110);
    private static final int COLOR_TEAL_SOFT = Color.rgb(224, 249, 241);
    private static final int COLOR_AMBER = Color.rgb(146, 64, 14);
    private static final int COLOR_AMBER_SOFT = Color.rgb(255, 251, 235);
    private static final int COLOR_RED = Color.rgb(190, 18, 60);
    private static final int COLOR_RED_SOFT = Color.rgb(255, 241, 242);

    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private SharedPreferences prefs;
    private String token;
    private String username;
    private String serverUrl;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().setStatusBarColor(COLOR_TEAL);
        getWindow().setNavigationBarColor(COLOR_INK);

        prefs = getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        token = prefs.getString(PREF_TOKEN, null);
        username = prefs.getString(PREF_USERNAME, "");
        serverUrl = normalizeServerUrl(prefs.getString(PREF_SERVER_URL, BuildConfig.SERVER_URL));
        if (serverUrl.isEmpty()) {
            serverUrl = normalizeServerUrl(BuildConfig.SERVER_URL);
        }

        if (token == null || token.trim().isEmpty()) {
            showLogin(null);
        } else {
            loadDashboard();
        }
    }

    private void showLogin(String errorMessage) {
        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(COLOR_BG);
        scrollView.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        scrollView.setTextDirection(View.TEXT_DIRECTION_RTL);

        LinearLayout root = column();
        root.setGravity(Gravity.CENTER_HORIZONTAL);
        root.setPadding(dp(18), dp(20), dp(18), dp(24));
        scrollView.addView(root, matchWrap());

        LinearLayout hero = column();
        hero.setPadding(dp(20), dp(20), dp(20), dp(20));
        hero.setBackground(cardBackground(COLOR_TEAL, COLOR_TEAL, 8));
        hero.setElevation(dp(2));
        root.addView(hero, matchWrap());

        LinearLayout heroTop = row();
        heroTop.setGravity(Gravity.CENTER_VERTICAL);
        hero.addView(heroTop, matchWrap());

        TextView mark = text("QIB", 18, COLOR_TEAL, Typeface.BOLD);
        mark.setGravity(Gravity.CENTER);
        mark.setBackground(cardBackground(Color.WHITE, Color.TRANSPARENT, 8));
        heroTop.addView(mark, widthHeight(dp(58), dp(46)));

        LinearLayout brand = column();
        TextView title = text("QIB ATM Manager", 26, Color.WHITE, Typeface.BOLD);
        title.setGravity(Gravity.RIGHT);
        brand.addView(title, matchWrap());
        heroTop.addView(brand, margin(weightWrap(1), 0, 0, dp(12), 0));

        LinearLayout apiCard = column();
        apiCard.setPadding(dp(16), dp(16), dp(16), dp(16));
        apiCard.setBackground(cardBackground(COLOR_CARD, colorWithAlpha(COLOR_TEAL, 80), 8));
        apiCard.setElevation(dp(1));
        root.addView(apiCard, margin(matchWrap(), 0, dp(12), 0, dp(12)));

        LinearLayout apiHeader = row();
        apiHeader.setGravity(Gravity.CENTER_VERTICAL);
        apiCard.addView(apiHeader, matchWrap());

        TextView apiLabel = text("عنوان API", 17, COLOR_INK, Typeface.BOLD);
        apiLabel.setGravity(Gravity.RIGHT);
        apiHeader.addView(apiLabel, weightWrap(1));
        apiHeader.addView(chip("جاهز", COLOR_TEAL, COLOR_TEAL_SOFT));

        LinearLayout apiAddress = row();
        apiAddress.setGravity(Gravity.CENTER_VERTICAL);
        apiCard.addView(apiAddress, margin(matchWrap(), 0, dp(12), 0, 0));

        TextView apiValue = text(serverUrl, 13, COLOR_MUTED, Typeface.NORMAL);
        apiValue.setGravity(Gravity.LEFT | Gravity.CENTER_VERTICAL);
        apiValue.setTextDirection(View.TEXT_DIRECTION_LTR);
        apiValue.setSingleLine(true);
        apiValue.setEllipsize(TextUtils.TruncateAt.MIDDLE);
        apiValue.setPadding(dp(12), 0, dp(12), 0);
        apiValue.setBackground(cardBackground(Color.rgb(248, 250, 252), Color.TRANSPARENT, 8));
        apiAddress.addView(apiValue, weightHeight(1, dp(46)));

        TextView apiSettingsButton = actionButton("تغيير", Color.WHITE, COLOR_TEAL, COLOR_TEAL);
        apiSettingsButton.setOnClickListener(view -> showApiSettingsDialog());
        apiAddress.addView(apiSettingsButton, margin(widthHeight(dp(86), dp(46)), dp(10), 0, 0, 0));

        LinearLayout card = column();
        card.setPadding(dp(20), dp(20), dp(20), dp(20));
        card.setBackground(cardBackground(COLOR_CARD, COLOR_LINE, 8));
        card.setElevation(dp(2));
        root.addView(card, matchWrap());

        TextView loginTitle = text("تسجيل الدخول", 22, COLOR_INK, Typeface.BOLD);
        loginTitle.setGravity(Gravity.RIGHT);
        card.addView(loginTitle, matchWrap());

        TextView loginSubtitle = text("استخدم حساب النظام للوصول إلى لوحة المراقبة.", 14, COLOR_MUTED, Typeface.NORMAL);
        loginSubtitle.setGravity(Gravity.RIGHT);
        card.addView(loginSubtitle, margin(matchWrap(), 0, dp(4), 0, dp(18)));

        EditText usernameInput = input("اسم المستخدم");
        usernameInput.setText(username == null ? "" : username);
        card.addView(labeledInput("اسم المستخدم", usernameInput), margin(matchWrap(), 0, 0, 0, dp(12)));

        EditText passwordInput = input("كلمة المرور");
        passwordInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        card.addView(labeledInput("كلمة المرور", passwordInput), margin(matchWrap(), 0, 0, 0, dp(14)));

        TextView error = text(errorMessage == null ? "" : errorMessage, 14, COLOR_RED, Typeface.NORMAL);
        error.setGravity(Gravity.RIGHT);
        error.setPadding(dp(12), dp(10), dp(12), dp(10));
        error.setBackground(cardBackground(COLOR_RED_SOFT, Color.rgb(254, 205, 211), 8));
        error.setVisibility(errorMessage == null ? View.GONE : View.VISIBLE);
        card.addView(error, margin(matchWrap(), 0, 0, 0, dp(12)));

        TextView loginButton = actionButton("تسجيل الدخول", Color.WHITE, COLOR_TEAL, COLOR_TEAL);
        card.addView(loginButton, matchHeight(dp(52)));

        loginButton.setOnClickListener(view -> {
            String enteredUsername = usernameInput.getText().toString().trim();
            String enteredPassword = passwordInput.getText().toString();
            if (enteredUsername.isEmpty() || enteredPassword.isEmpty()) {
                error.setText("أدخل اسم المستخدم وكلمة المرور.");
                error.setVisibility(View.VISIBLE);
                return;
            }
            performLogin(enteredUsername, enteredPassword);
        });

        setContentView(scrollView);
    }

    private void showApiSettingsDialog() {
        LinearLayout body = column();
        body.setPadding(dp(4), dp(8), dp(4), dp(4));

        TextView hint = text("أدخل عنوان API كاملاً. مثال: http://172.16.23.34:8001", 13, COLOR_MUTED, Typeface.NORMAL);
        hint.setGravity(Gravity.RIGHT);
        body.addView(hint, margin(matchWrap(), 0, 0, 0, dp(10)));

        EditText serverInput = input("عنوان API");
        serverInput.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        serverInput.setText(serverUrl);
        serverInput.setGravity(Gravity.LEFT | Gravity.CENTER_VERTICAL);
        serverInput.setTextDirection(View.TEXT_DIRECTION_LTR);
        body.addView(serverInput, matchHeight(dp(52)));

        TextView warning = text("عند تغيير العنوان سيتم تسجيل الخروج من الجلسة الحالية.", 12, COLOR_AMBER, Typeface.NORMAL);
        warning.setGravity(Gravity.RIGHT);
        body.addView(warning, margin(matchWrap(), 0, dp(10), 0, 0));

        AlertDialog dialog = new AlertDialog.Builder(this)
            .setTitle("إعدادات API")
            .setView(body)
            .setNegativeButton("إلغاء", null)
            .setPositiveButton("حفظ", null)
            .create();

        dialog.setOnShowListener(d -> {
            Button save = dialog.getButton(AlertDialog.BUTTON_POSITIVE);
            Button cancel = dialog.getButton(AlertDialog.BUTTON_NEGATIVE);
            if (save != null) {
                save.setTextColor(COLOR_TEAL);
                save.setOnClickListener(view -> {
                    String normalized = normalizeServerUrl(serverInput.getText().toString());
                    if (!isValidServerUrl(normalized)) {
                        serverInput.setError("اكتب عنواناً يبدأ بـ http:// أو https://");
                        return;
                    }

                    boolean changed = !normalized.equals(serverUrl);
                    serverUrl = normalized;
                    SharedPreferences.Editor editor = prefs.edit().putString(PREF_SERVER_URL, serverUrl);
                    if (changed) {
                        token = null;
                        editor.remove(PREF_TOKEN);
                    }
                    editor.apply();
                    dialog.dismiss();
                    Toast.makeText(this, "تم حفظ عنوان API", Toast.LENGTH_SHORT).show();
                    showLogin(changed ? "تم تحديث عنوان API. سجّل الدخول مرة أخرى." : null);
                });
            }
            if (cancel != null) {
                cancel.setTextColor(COLOR_MUTED);
            }
        });
        dialog.show();
    }

    private void performLogin(String enteredUsername, String enteredPassword) {
        showBlockingStatus("جاري تسجيل الدخول", "يتم الاتصال بالسيرفر عبر API.");
        executor.execute(() -> {
            try {
                JSONObject payload = new JSONObject();
                payload.put("username", enteredUsername);
                payload.put("password", enteredPassword);

                String response = request("/api/auth/login", "POST", payload.toString(), null);
                JSONObject json = new JSONObject(response);
                String accessToken = json.getString("access_token");

                token = accessToken;
                username = enteredUsername;
                prefs.edit()
                    .putString(PREF_TOKEN, token)
                    .putString(PREF_USERNAME, username)
                    .apply();

                mainHandler.post(this::loadDashboard);
            } catch (Exception exception) {
                mainHandler.post(() -> showLogin(friendlyError(exception)));
            }
        });
    }

    private void loadDashboard() {
        showBlockingStatus("جاري تحميل البيانات", "API: " + serverUrl);
        executor.execute(() -> {
            try {
                List<AtmItem> atms = parseAtms(request("/api/atms", "GET", null, token));
                CashSummary summary = parseCashSummary(request("/api/cash/summary", "GET", null, token));
                mainHandler.post(() -> showDashboard(atms, summary));
            } catch (ApiException exception) {
                if (exception.statusCode == 401) {
                    clearSession();
                    mainHandler.post(() -> showLogin("انتهت الجلسة أو بيانات الدخول غير صحيحة. سجّل الدخول مرة أخرى."));
                } else {
                    mainHandler.post(() -> showErrorScreen("تعذر تحميل البيانات", friendlyError(exception)));
                }
            } catch (Exception exception) {
                mainHandler.post(() -> showErrorScreen("تعذر تحميل البيانات", friendlyError(exception)));
            }
        });
    }

    private void showDashboard(List<AtmItem> atms, CashSummary summary) {
        int onlineCount = 0;
        for (AtmItem atm : atms) {
            if (atm.isOnline) {
                onlineCount++;
            }
        }
        int offlineCount = Math.max(0, atms.size() - onlineCount);

        ScrollView scrollView = new ScrollView(this);
        scrollView.setFillViewport(true);
        scrollView.setBackgroundColor(COLOR_BG);
        scrollView.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        scrollView.setTextDirection(View.TEXT_DIRECTION_RTL);

        LinearLayout root = column();
        root.setPadding(dp(14), dp(14), dp(14), dp(22));
        scrollView.addView(root, matchWrap());

        LinearLayout headerCard = column();
        headerCard.setPadding(dp(16), dp(15), dp(16), dp(15));
        headerCard.setBackground(cardBackground(COLOR_CARD, COLOR_LINE, 8));
        root.addView(headerCard, matchWrap());

        LinearLayout header = row();
        header.setGravity(Gravity.CENTER_VERTICAL);
        headerCard.addView(header, matchWrap());

        LinearLayout titleBox = column();
        TextView title = text("لوحة التحكم", 25, COLOR_INK, Typeface.BOLD);
        title.setGravity(Gravity.RIGHT);
        titleBox.addView(title, matchWrap());
        TextView meta = text("QIB ATM Manager · API مباشر", 13, COLOR_MUTED, Typeface.NORMAL);
        meta.setGravity(Gravity.RIGHT);
        titleBox.addView(meta, matchWrap());
        header.addView(titleBox, weightWrap(1));

        TextView userPill = chip(emptyToDash(username), COLOR_TEAL, COLOR_TEAL_SOFT);
        header.addView(userPill, margin(widthHeight(dp(104), dp(38)), dp(10), 0, 0, 0));

        LinearLayout actions = row();
        actions.setGravity(Gravity.CENTER_VERTICAL);
        headerCard.addView(actions, margin(matchWrap(), 0, dp(14), 0, 0));

        Button refresh = secondaryButton("تحديث");
        refresh.setOnClickListener(view -> loadDashboard());
        actions.addView(refresh, weightHeight(1, dp(44)));

        Button logout = ghostButton("خروج");
        logout.setOnClickListener(view -> {
            clearSession();
            showLogin(null);
        });
        actions.addView(logout, margin(weightHeight(1, dp(44)), dp(10), 0, 0, 0));

        TextView api = text(serverUrl, 12, COLOR_MUTED, Typeface.NORMAL);
        api.setGravity(Gravity.LEFT | Gravity.CENTER_VERTICAL);
        api.setTextDirection(View.TEXT_DIRECTION_LTR);
        headerCard.addView(api, margin(matchWrap(), 0, dp(10), 0, 0));

        root.addView(summaryGrid(onlineCount, offlineCount, summary), margin(matchWrap(), 0, dp(16), 0, dp(14)));

        LinearLayout listHeader = row();
        listHeader.setGravity(Gravity.CENTER_VERTICAL);
        TextView listTitle = text("الصرافات", 20, COLOR_INK, Typeface.BOLD);
        listTitle.setGravity(Gravity.RIGHT);
        listHeader.addView(listTitle, weightWrap(1));
        listHeader.addView(chip(String.valueOf(atms.size()), COLOR_MUTED, Color.rgb(248, 250, 252)));
        root.addView(listHeader, margin(matchWrap(), 0, 0, 0, dp(8)));

        if (atms.isEmpty()) {
            TextView empty = text("لا توجد صرافات حالياً.", 15, COLOR_MUTED, Typeface.NORMAL);
            empty.setGravity(Gravity.CENTER);
            empty.setPadding(dp(18), dp(24), dp(18), dp(24));
            empty.setBackground(cardBackground(COLOR_CARD, COLOR_LINE, 8));
            root.addView(empty, matchWrap());
        } else {
            for (AtmItem atm : atms) {
                root.addView(atmCard(atm), margin(matchWrap(), 0, 0, 0, dp(10)));
            }
        }

        setContentView(scrollView);
    }

    private LinearLayout summaryGrid(int onlineCount, int offlineCount, CashSummary summary) {
        LinearLayout grid = column();
        LinearLayout overview = column();
        overview.setPadding(dp(14), dp(14), dp(14), dp(14));
        overview.setBackground(cardBackground(COLOR_CARD, COLOR_LINE, 8));
        grid.addView(overview, matchWrap());

        TextView overviewTitle = text("نظرة عامة", 16, COLOR_INK, Typeface.BOLD);
        overviewTitle.setGravity(Gravity.RIGHT);
        overview.addView(overviewTitle, matchWrap());

        LinearLayout overviewRow = row();
        overview.addView(overviewRow, margin(matchWrap(), 0, dp(10), 0, 0));
        overviewRow.addView(summaryCard("Online", String.valueOf(onlineCount), COLOR_TEAL, COLOR_TEAL_SOFT), weightHeight(1, dp(96)));
        overviewRow.addView(summaryCard("Offline", String.valueOf(offlineCount), offlineCount > 0 ? COLOR_RED : COLOR_MUTED, offlineCount > 0 ? COLOR_RED_SOFT : Color.rgb(248, 250, 252)), margin(weightHeight(1, dp(96)), dp(10), 0, 0, 0));

        LinearLayout cashPanel = column();
        cashPanel.setPadding(dp(14), dp(14), dp(14), dp(14));
        cashPanel.setBackground(cardBackground(COLOR_CARD, COLOR_LINE, 8));
        grid.addView(cashPanel, margin(matchWrap(), 0, dp(12), 0, 0));

        LinearLayout cashHeader = row();
        cashHeader.setGravity(Gravity.CENTER_VERTICAL);
        TextView cashTitle = text("حالة النقد", 16, COLOR_INK, Typeface.BOLD);
        cashTitle.setGravity(Gravity.RIGHT);
        cashHeader.addView(cashTitle, weightWrap(1));
        cashHeader.addView(chip("تنبيهات " + summary.openAlerts, summary.openAlerts > 0 ? COLOR_AMBER : COLOR_TEAL, summary.openAlerts > 0 ? COLOR_AMBER_SOFT : COLOR_TEAL_SOFT));
        cashPanel.addView(cashHeader, matchWrap());

        cashPanel.addView(summaryRow(
            summaryCard("Low", String.valueOf(summary.cashLowAtms), summary.cashLowAtms > 0 ? COLOR_AMBER : COLOR_TEAL, summary.cashLowAtms > 0 ? COLOR_AMBER_SOFT : COLOR_TEAL_SOFT),
            summaryCard("Empty", String.valueOf(summary.cashEmptyAtms), summary.cashEmptyAtms > 0 ? COLOR_RED : COLOR_TEAL, summary.cashEmptyAtms > 0 ? COLOR_RED_SOFT : COLOR_TEAL_SOFT)
        ), margin(matchWrap(), 0, dp(10), 0, 0));

        LinearLayout criticalRow = row();
        criticalRow.setGravity(Gravity.CENTER_VERTICAL);
        criticalRow.setPadding(dp(12), dp(10), dp(12), dp(10));
        criticalRow.setBackground(cardBackground(Color.rgb(248, 250, 252), Color.TRANSPARENT, 8));
        TextView criticalLabel = text("Cash Critical", 13, COLOR_MUTED, Typeface.BOLD);
        criticalLabel.setGravity(Gravity.RIGHT);
        criticalRow.addView(criticalLabel, weightWrap(1));
        TextView criticalValue = text(String.valueOf(summary.cashCriticalAtms), 18, summary.cashCriticalAtms > 0 ? COLOR_RED : COLOR_TEAL, Typeface.BOLD);
        criticalValue.setGravity(Gravity.LEFT);
        criticalRow.addView(criticalValue, widthHeight(dp(56), dp(30)));
        cashPanel.addView(criticalRow, margin(matchWrap(), 0, dp(10), 0, 0));
        return grid;
    }

    private LinearLayout summaryRow(View left, View right) {
        LinearLayout row = row();
        row.addView(right, weightHeight(1, dp(92)));
        row.addView(left, margin(weightHeight(1, dp(92)), dp(10), 0, 0, 0));
        return row;
    }

    private LinearLayout summaryCard(String label, String value, int color, int fill) {
        LinearLayout card = column();
        card.setGravity(Gravity.RIGHT | Gravity.CENTER_VERTICAL);
        card.setPadding(dp(12), dp(10), dp(12), dp(10));
        card.setBackground(cardBackground(fill, colorWithAlpha(color, 90), 8));

        TextView labelView = text(label, 12, COLOR_MUTED, Typeface.BOLD);
        labelView.setGravity(Gravity.RIGHT);
        TextView valueView = text(value, 30, color, Typeface.BOLD);
        valueView.setGravity(Gravity.RIGHT);

        card.addView(labelView, matchWrap());
        card.addView(valueView, matchWrap());
        return card;
    }

    private View atmCard(AtmItem atm) {
        LinearLayout card = column();
        int statusColor = atm.isOnline ? COLOR_TEAL : COLOR_RED;
        int statusFill = atm.isOnline ? COLOR_TEAL_SOFT : COLOR_RED_SOFT;
        card.setPadding(dp(14), dp(13), dp(14), dp(13));
        card.setBackground(cardBackground(COLOR_CARD, colorWithAlpha(statusColor, atm.isOnline ? 80 : 120), 8));
        card.setClickable(true);
        card.setOnClickListener(view -> loadAtmDetails(atm));

        LinearLayout top = row();
        top.setGravity(Gravity.CENTER_VERTICAL);
        card.addView(top, matchWrap());

        LinearLayout titleBox = column();
        TextView name = text(atm.name, 19, COLOR_INK, Typeface.BOLD);
        name.setGravity(Gravity.RIGHT);
        titleBox.addView(name, matchWrap());
        TextView branch = text(atm.branch + " · " + atm.vpnIp, 12, COLOR_MUTED, Typeface.NORMAL);
        branch.setGravity(Gravity.RIGHT);
        titleBox.addView(branch, matchWrap());
        top.addView(titleBox, weightWrap(1));

        top.addView(chip(atm.isOnline ? "متصل" : "غير متصل", statusColor, statusFill));

        LinearLayout idRow = row();
        idRow.setGravity(Gravity.CENTER_VERTICAL);
        card.addView(idRow, margin(matchWrap(), 0, dp(12), 0, 0));
        idRow.addView(chip(atm.atmId, COLOR_MUTED, Color.rgb(248, 250, 252)));
        TextView service = text(emptyToDash(atm.status), 12, COLOR_MUTED, Typeface.BOLD);
        service.setGravity(Gravity.LEFT | Gravity.CENTER_VERTICAL);
        idRow.addView(service, margin(weightWrap(1), dp(8), 0, 0, 0));

        LinearLayout facts = row();
        facts.setGravity(Gravity.CENTER_VERTICAL);
        card.addView(facts, margin(matchWrap(), 0, dp(10), 0, 0));

        facts.addView(miniFact("Latency", atm.latencyMs > 0 ? atm.latencyMs + " ms" : "-"), weightWrap(1));
        facts.addView(miniFact("Agent", emptyToDash(atm.agentVersion)), margin(weightWrap(1), dp(8), 0, 0, 0));

        LinearLayout statusRow = row();
        statusRow.setGravity(Gravity.CENTER_VERTICAL);
        card.addView(statusRow, margin(matchWrap(), 0, dp(8), 0, 0));
        statusRow.addView(miniFact("Cash", emptyToDash(atm.cashStatus)), weightWrap(1));
        TextView hint = text("تفاصيل النقد", 12, COLOR_TEAL, Typeface.BOLD);
        hint.setGravity(Gravity.CENTER);
        hint.setPadding(dp(10), dp(8), dp(10), dp(8));
        hint.setBackground(cardBackground(COLOR_TEAL_SOFT, Color.TRANSPARENT, 8));
        statusRow.addView(hint, margin(widthHeight(dp(112), dp(40)), dp(8), 0, 0, 0));
        return card;
    }

    private LinearLayout miniFact(String label, String value) {
        LinearLayout box = column();
        box.setPadding(dp(10), dp(8), dp(10), dp(8));
        box.setBackground(cardBackground(Color.rgb(248, 250, 252), Color.TRANSPARENT, 8));
        TextView labelView = text(label, 11, COLOR_MUTED, Typeface.BOLD);
        labelView.setGravity(Gravity.RIGHT);
        TextView valueView = text(value, 13, COLOR_INK, Typeface.BOLD);
        valueView.setGravity(Gravity.RIGHT);
        box.addView(labelView, matchWrap());
        box.addView(valueView, matchWrap());
        return box;
    }

    private void loadAtmDetails(AtmItem atm) {
        Toast.makeText(this, "جاري قراءة تفاصيل " + atm.name, Toast.LENGTH_SHORT).show();
        executor.execute(() -> {
            try {
                String encodedAtmId = URLEncoder.encode(atm.atmId, "UTF-8");
                CashDetails details = parseCashDetails(request("/api/cash/atms/" + encodedAtmId, "GET", null, token));
                mainHandler.post(() -> showCashDetailsDialog(atm, details));
            } catch (Exception exception) {
                mainHandler.post(() -> Toast.makeText(this, friendlyError(exception), Toast.LENGTH_LONG).show());
            }
        });
    }

    private void showCashDetailsDialog(AtmItem atm, CashDetails details) {
        ScrollView scrollView = new ScrollView(this);
        scrollView.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        scrollView.setTextDirection(View.TEXT_DIRECTION_RTL);
        scrollView.setBackgroundColor(COLOR_BG);

        LinearLayout body = column();
        body.setPadding(dp(12), dp(12), dp(12), dp(12));
        scrollView.addView(body, matchWrap());

        LinearLayout header = column();
        header.setPadding(dp(16), dp(14), dp(16), dp(14));
        header.setBackground(cardBackground(COLOR_CARD, COLOR_LINE, 8));
        body.addView(header, matchWrap());

        TextView title = text(atm.name, 22, COLOR_INK, Typeface.BOLD);
        title.setGravity(Gravity.RIGHT);
        header.addView(title, matchWrap());

        TextView subtitle = text(atm.branch + " · " + atm.vpnIp + " · " + atm.atmId, 13, COLOR_MUTED, Typeface.NORMAL);
        subtitle.setGravity(Gravity.RIGHT);
        header.addView(subtitle, margin(matchWrap(), 0, dp(4), 0, dp(10)));

        LinearLayout statusLine = row();
        statusLine.setGravity(Gravity.CENTER_VERTICAL);
        header.addView(statusLine, matchWrap());
        statusLine.addView(chip(atm.isOnline ? "متصل" : "غير متصل", atm.isOnline ? COLOR_TEAL : COLOR_RED, atm.isOnline ? COLOR_TEAL_SOFT : COLOR_RED_SOFT));
        statusLine.addView(chip("Cash: " + emptyToDash(atm.cashStatus), COLOR_TEAL, COLOR_TEAL_SOFT), margin(weightWrap(1), dp(8), 0, 0, 0));

        if (!details.units.isEmpty()) {
            body.addView(cashTotalsPanel(details), margin(matchWrap(), 0, dp(10), 0, dp(10)));
        }

        if (details.rejectRetract != null) {
            LinearLayout rr = row();
            rr.addView(detailMetric("Reject Bin", String.valueOf(details.rejectRetract.rejectCount), "Capacity " + details.rejectRetract.rejectMaxCapacity, details.rejectRetract.rejectCount > 0 ? COLOR_AMBER : COLOR_TEAL), weightHeight(1, dp(98)));
            rr.addView(detailMetric("Retract Bin", String.valueOf(details.rejectRetract.retractCount), "Capacity " + details.rejectRetract.retractMaxCapacity, details.rejectRetract.retractCount > 0 ? COLOR_AMBER : COLOR_TEAL), margin(weightHeight(1, dp(98)), dp(8), 0, 0, 0));
            body.addView(rr, margin(matchWrap(), 0, 0, 0, dp(12)));
        }

        if (details.units.isEmpty()) {
            TextView empty = text("لا توجد قراءة نقد محفوظة لهذا الصراف.", 15, COLOR_MUTED, Typeface.NORMAL);
            empty.setGravity(Gravity.CENTER);
            empty.setPadding(dp(12), dp(22), dp(12), dp(22));
            empty.setBackground(cardBackground(Color.rgb(248, 250, 252), COLOR_LINE, 8));
            body.addView(empty, matchWrap());
        } else {
            LinearLayout sectionHeader = row();
            sectionHeader.setGravity(Gravity.CENTER_VERTICAL);
            TextView unitsTitle = text("صناديق النقد", 18, COLOR_INK, Typeface.BOLD);
            unitsTitle.setGravity(Gravity.RIGHT);
            sectionHeader.addView(unitsTitle, weightWrap(1));
            sectionHeader.addView(chip(String.valueOf(details.units.size()), COLOR_MUTED, Color.rgb(248, 250, 252)));
            body.addView(sectionHeader, margin(matchWrap(), 0, 0, 0, dp(8)));

            for (CashUnit unit : details.units) {
                body.addView(cashUnitRow(unit), margin(matchWrap(), 0, 0, 0, dp(8)));
            }
        }

        AlertDialog dialog = new AlertDialog.Builder(this)
            .setView(scrollView)
            .setNegativeButton("إغلاق", null)
            .setPositiveButton("قراءة الآن", (dialogInterface, which) -> requestCashReadNow(atm))
            .create();
        dialog.setOnShowListener(d -> {
            Button positive = dialog.getButton(AlertDialog.BUTTON_POSITIVE);
            Button negative = dialog.getButton(AlertDialog.BUTTON_NEGATIVE);
            if (positive != null) {
                positive.setTextColor(COLOR_TEAL);
            }
            if (negative != null) {
                negative.setTextColor(COLOR_MUTED);
            }
        });
        dialog.show();
    }

    private LinearLayout cashTotalsPanel(CashDetails details) {
        LinearLayout panel = column();
        panel.setPadding(dp(14), dp(12), dp(14), dp(12));
        panel.setBackground(cardBackground(COLOR_CARD, COLOR_LINE, 8));

        TextView title = text("ملخص النقد", 16, COLOR_INK, Typeface.BOLD);
        title.setGravity(Gravity.RIGHT);
        panel.addView(title, matchWrap());

        LinearLayout row = row();
        row.setGravity(Gravity.CENTER_VERTICAL);
        panel.addView(row, margin(matchWrap(), 0, dp(10), 0, 0));
        row.addView(metricText("الصناديق", String.valueOf(details.units.size())), weightWrap(1));
        row.addView(metricText("الأوراق", String.valueOf(totalNoteCount(details))), margin(weightWrap(1), dp(8), 0, 0, 0));
        row.addView(metricText("منخفض/فارغ", riskUnitCount(details)), margin(weightWrap(1), dp(8), 0, 0, 0));
        return panel;
    }

    private LinearLayout detailMetric(String label, String value, String meta, int color) {
        LinearLayout card = column();
        card.setPadding(dp(12), dp(10), dp(12), dp(10));
        card.setBackground(cardBackground(color == COLOR_TEAL ? COLOR_TEAL_SOFT : COLOR_AMBER_SOFT, Color.TRANSPARENT, 8));
        TextView labelView = text(label, 13, COLOR_MUTED, Typeface.BOLD);
        labelView.setGravity(Gravity.RIGHT);
        TextView valueView = text(value, 28, color, Typeface.BOLD);
        valueView.setGravity(Gravity.RIGHT);
        TextView metaView = text(meta, 12, COLOR_MUTED, Typeface.NORMAL);
        metaView.setGravity(Gravity.RIGHT);
        card.addView(labelView, matchWrap());
        card.addView(valueView, matchWrap());
        card.addView(metaView, matchWrap());
        return card;
    }

    private LinearLayout cashUnitRow(CashUnit unit) {
        CashUnitTone tone = cashUnitTone(unit);
        LinearLayout row = column();
        row.setPadding(dp(12), dp(11), dp(12), dp(11));
        row.setBackground(cardBackground(tone.fill, colorWithAlpha(tone.color, 70), 8));

        LinearLayout first = row();
        first.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(first, matchWrap());

        LinearLayout titleBox = column();
        TextView title = text("Cassette " + unit.cassetteNo, 17, COLOR_INK, Typeface.BOLD);
        title.setGravity(Gravity.RIGHT);
        titleBox.addView(title, matchWrap());
        TextView cash = text(unit.expectedCurrency + " " + unit.expectedDenomination + " · آخر قراءة " + cleanDate(unit.readAt), 12, COLOR_MUTED, Typeface.NORMAL);
        cash.setGravity(Gravity.RIGHT);
        titleBox.addView(cash, matchWrap());
        first.addView(titleBox, weightWrap(1));

        first.addView(chip(tone.label, tone.color, Color.WHITE));

        LinearLayout counts = row();
        counts.setGravity(Gravity.CENTER_VERTICAL);
        row.addView(counts, margin(matchWrap(), 0, dp(10), 0, 0));
        counts.addView(metricText("Current", unit.currentCount + "/" + unit.maxCapacity), weightWrap(1));
        counts.addView(metricText("Rejects", String.valueOf(unit.rejectCount)), margin(weightWrap(1), dp(8), 0, 0, 0));
        counts.addView(metricText("Low / Critical", unit.lowThreshold + " / " + unit.criticalThreshold), margin(weightWrap(1), dp(8), 0, 0, 0));

        LinearLayout progressTrack = row();
        progressTrack.setBackground(cardBackground(Color.WHITE, Color.TRANSPARENT, 12));
        row.addView(progressTrack, margin(matchHeight(dp(8)), 0, dp(10), 0, 0));
        View progress = new View(this);
        progress.setBackground(cardBackground(tone.color, Color.TRANSPARENT, 12));
        progressTrack.addView(progress, widthHeight(dp(cashUnitProgressWidth(unit)), dp(8)));
        return row;
    }

    private LinearLayout metricText(String label, String value) {
        LinearLayout box = column();
        TextView labelView = text(label, 11, COLOR_MUTED, Typeface.BOLD);
        labelView.setGravity(Gravity.RIGHT);
        TextView valueView = text(value, 15, COLOR_INK, Typeface.BOLD);
        valueView.setGravity(Gravity.RIGHT);
        box.addView(labelView, matchWrap());
        box.addView(valueView, matchWrap());
        return box;
    }

    private int totalNoteCount(CashDetails details) {
        int total = 0;
        for (CashUnit unit : details.units) {
            total += Math.max(0, unit.currentCount);
        }
        return total;
    }

    private String riskUnitCount(CashDetails details) {
        int risky = 0;
        for (CashUnit unit : details.units) {
            CashUnitTone tone = cashUnitTone(unit);
            if (!"OK".equals(tone.label)) {
                risky++;
            }
        }
        return risky + "/" + details.units.size();
    }

    private CashUnitTone cashUnitTone(CashUnit unit) {
        if (unit.currentCount <= 0) {
            return new CashUnitTone("EMPTY", COLOR_RED, COLOR_RED_SOFT);
        }
        if (unit.criticalThreshold > 0 && unit.currentCount <= unit.criticalThreshold) {
            return new CashUnitTone("CRITICAL", COLOR_RED, COLOR_RED_SOFT);
        }
        if (unit.lowThreshold > 0 && unit.currentCount <= unit.lowThreshold) {
            return new CashUnitTone("LOW", COLOR_AMBER, COLOR_AMBER_SOFT);
        }
        if (!unit.status.equalsIgnoreCase("OK")) {
            return new CashUnitTone(unit.status, COLOR_AMBER, COLOR_AMBER_SOFT);
        }
        return new CashUnitTone("OK", COLOR_TEAL, COLOR_TEAL_SOFT);
    }

    private int cashUnitProgressWidth(CashUnit unit) {
        int capacity = Math.max(1, unit.maxCapacity);
        float ratio = Math.max(0f, Math.min(1f, (float) unit.currentCount / (float) capacity));
        return Math.max(12, Math.round(260f * ratio));
    }

    private void requestCashReadNow(AtmItem atm) {
        Toast.makeText(this, "تم إرسال طلب قراءة إلى " + atm.name, Toast.LENGTH_SHORT).show();
        executor.execute(() -> {
            try {
                String encodedAtmId = URLEncoder.encode(atm.atmId, "UTF-8");
                request("/api/cash/atms/" + encodedAtmId + "/read-now", "POST", null, token);
                mainHandler.post(() -> Toast.makeText(this, "تم قبول طلب القراءة.", Toast.LENGTH_LONG).show());
            } catch (Exception exception) {
                mainHandler.post(() -> Toast.makeText(this, friendlyError(exception), Toast.LENGTH_LONG).show());
            }
        });
    }

    private void showBlockingStatus(String title, String message) {
        FrameLayout frame = new FrameLayout(this);
        frame.setBackgroundColor(COLOR_BG);
        frame.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        frame.setTextDirection(View.TEXT_DIRECTION_RTL);

        LinearLayout body = column();
        body.setGravity(Gravity.CENTER);
        body.setPadding(dp(28), dp(28), dp(28), dp(28));

        ProgressBar progress = new ProgressBar(this);
        body.addView(progress, widthHeight(dp(54), dp(54)));

        TextView titleView = text(title, 22, COLOR_INK, Typeface.BOLD);
        titleView.setGravity(Gravity.CENTER);
        body.addView(titleView, margin(matchWrap(), 0, dp(18), 0, 0));

        TextView messageView = text(message, 14, COLOR_MUTED, Typeface.NORMAL);
        messageView.setGravity(Gravity.CENTER);
        body.addView(messageView, margin(matchWrap(), 0, dp(8), 0, 0));

        frame.addView(body, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));
        setContentView(frame);
    }

    private void showErrorScreen(String title, String message) {
        LinearLayout root = column();
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(24), dp(24), dp(24), dp(24));
        root.setBackgroundColor(COLOR_BG);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        root.setTextDirection(View.TEXT_DIRECTION_RTL);

        TextView titleView = text(title, 23, COLOR_INK, Typeface.BOLD);
        titleView.setGravity(Gravity.CENTER);
        root.addView(titleView, matchWrap());

        TextView messageView = text(message, 15, COLOR_MUTED, Typeface.NORMAL);
        messageView.setGravity(Gravity.CENTER);
        root.addView(messageView, margin(matchWrap(), 0, dp(12), 0, dp(18)));

        Button retry = primaryButton("إعادة المحاولة");
        retry.setOnClickListener(view -> loadDashboard());
        root.addView(retry, matchHeight(dp(50)));

        Button logout = ghostButton("تسجيل دخول جديد");
        logout.setOnClickListener(view -> {
            clearSession();
            showLogin(null);
        });
        root.addView(logout, margin(matchHeight(dp(48)), 0, dp(8), 0, 0));

        Button apiSettings = ghostButton("إعدادات API");
        apiSettings.setOnClickListener(view -> showApiSettingsDialog());
        root.addView(apiSettings, margin(matchHeight(dp(48)), 0, dp(8), 0, 0));

        setContentView(root);
    }

    private String request(String path, String method, String body, String bearerToken) throws Exception {
        URL url = new URL(serverUrl + path);
        HttpURLConnection connection = (HttpURLConnection) url.openConnection();
        connection.setRequestMethod(method);
        connection.setConnectTimeout(12000);
        connection.setReadTimeout(20000);
        connection.setRequestProperty("Accept", "application/json");
        if (bearerToken != null && !bearerToken.trim().isEmpty()) {
            connection.setRequestProperty("Authorization", "Bearer " + bearerToken);
        }
        if (body != null) {
            byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
            connection.setDoOutput(true);
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8");
            connection.setFixedLengthStreamingMode(bytes.length);
            try (OutputStream output = connection.getOutputStream()) {
                output.write(bytes);
            }
        }

        int statusCode = connection.getResponseCode();
        InputStream stream = statusCode >= 400 ? connection.getErrorStream() : connection.getInputStream();
        String response = readStream(stream);
        connection.disconnect();

        if (statusCode >= 400) {
            throw new ApiException(statusCode, response);
        }
        return response;
    }

    private String readStream(InputStream stream) throws Exception {
        if (stream == null) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        try (BufferedReader reader = new BufferedReader(new InputStreamReader(stream, StandardCharsets.UTF_8))) {
            String line;
            while ((line = reader.readLine()) != null) {
                builder.append(line);
            }
        }
        return builder.toString();
    }

    private List<AtmItem> parseAtms(String response) throws Exception {
        JSONArray array = new JSONArray(response);
        List<AtmItem> atms = new ArrayList<>();
        for (int i = 0; i < array.length(); i++) {
            JSONObject item = array.getJSONObject(i);
            JSONObject modules = item.optJSONObject("module_status_json");
            String cashStatus = modules == null ? "" : modules.optString("cash_monitoring", "");
            atms.add(new AtmItem(
                item.optString("atm_id", "-"),
                item.optString("name", "-"),
                item.optString("branch", "-"),
                item.optString("vpn_ip", "-"),
                item.optString("status", "-"),
                item.optBoolean("is_online", false),
                item.optString("agent_version", ""),
                item.optInt("latency_ms", 0),
                cashStatus
            ));
        }
        return atms;
    }

    private CashSummary parseCashSummary(String response) throws Exception {
        JSONObject json = new JSONObject(response);
        return new CashSummary(
            json.optInt("cash_low_atms", 0),
            json.optInt("cash_empty_atms", 0),
            json.optInt("cash_critical_atms", 0),
            json.optInt("open_alerts", 0)
        );
    }

    private CashDetails parseCashDetails(String response) throws Exception {
        JSONObject json = new JSONObject(response);
        CashDetails details = new CashDetails();

        JSONObject rejectRetract = json.optJSONObject("reject_retract");
        if (rejectRetract != null) {
            details.rejectRetract = new RejectRetract(
                rejectRetract.optInt("reject_count", 0),
                rejectRetract.optInt("retract_count", 0),
                rejectRetract.optInt("reject_max_capacity", 0),
                rejectRetract.optInt("retract_max_capacity", 0)
            );
        }

        JSONArray units = json.optJSONArray("units");
        if (units != null) {
            for (int i = 0; i < units.length(); i++) {
                JSONObject unit = units.getJSONObject(i);
                details.units.add(new CashUnit(
                    unit.optInt("cassette_no", 0),
                    unit.optString("expected_currency", unit.optString("reported_currency", "")),
                    unit.optInt("expected_denomination", unit.optInt("reported_denomination", 0)),
                    unit.optInt("current_count", 0),
                    unit.optInt("reject_count", 0),
                    unit.optInt("low_threshold", 0),
                    unit.optInt("critical_threshold", 0),
                    unit.optInt("max_capacity", 1),
                    unit.optString("status", "-"),
                    unit.optString("read_at", "")
                ));
            }
        }
        return details;
    }

    private void clearSession() {
        token = null;
        prefs.edit().remove(PREF_TOKEN).apply();
    }

    private String normalizeServerUrl(String value) {
        String cleaned = value == null ? "" : value.trim();
        String lower = cleaned.toLowerCase();
        if (!cleaned.isEmpty() && !lower.startsWith("http://") && !lower.startsWith("https://")) {
            cleaned = "http://" + cleaned;
        }
        while (cleaned.endsWith("/")) {
            cleaned = cleaned.substring(0, cleaned.length() - 1);
        }
        return cleaned;
    }

    private boolean isValidServerUrl(String value) {
        if (value == null) {
            return false;
        }
        String lower = value.toLowerCase();
        return (lower.startsWith("http://") && value.length() > "http://".length())
            || (lower.startsWith("https://") && value.length() > "https://".length());
    }

    private String friendlyError(Exception exception) {
        if (exception instanceof ApiException) {
            ApiException apiException = (ApiException) exception;
            String detail = apiException.detail();
            if (detail.isEmpty()) {
                detail = "HTTP " + apiException.statusCode;
            }
            return detail;
        }
        String message = exception.getMessage();
        if (message == null || message.trim().isEmpty()) {
            return "حدث خطأ غير معروف.";
        }
        return message;
    }

    private String emptyToDash(String value) {
        if (value == null || value.trim().isEmpty() || value.equals("null")) {
            return "-";
        }
        return value;
    }

    private String cleanDate(String value) {
        if (value == null || value.trim().isEmpty() || value.equals("null")) {
            return "-";
        }
        String cleaned = value.replace("T", " ");
        int dot = cleaned.indexOf('.');
        if (dot > 0) {
            cleaned = cleaned.substring(0, dot);
        }
        return cleaned;
    }

    private LinearLayout column() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        layout.setTextDirection(View.TEXT_DIRECTION_RTL);
        return layout;
    }

    private LinearLayout row() {
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.HORIZONTAL);
        layout.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        layout.setTextDirection(View.TEXT_DIRECTION_RTL);
        return layout;
    }

    private TextView text(String value, int sizeSp, int color, int style) {
        TextView textView = new TextView(this);
        textView.setText(value);
        textView.setTextSize(sizeSp);
        textView.setTextColor(color);
        textView.setTypeface(Typeface.DEFAULT, style);
        textView.setIncludeFontPadding(true);
        textView.setTextDirection(View.TEXT_DIRECTION_RTL);
        return textView;
    }

    private TextView chip(String value, int color, int fill) {
        TextView textView = text(value, 13, color, Typeface.BOLD);
        textView.setGravity(Gravity.CENTER);
        textView.setPadding(dp(12), dp(7), dp(12), dp(7));
        textView.setBackground(cardBackground(fill, Color.TRANSPARENT, 24));
        return textView;
    }

    private TextView loginBadge(String value) {
        TextView badge = text(value, 12, Color.rgb(204, 251, 241), Typeface.BOLD);
        badge.setGravity(Gravity.CENTER);
        badge.setPadding(dp(12), dp(7), dp(12), dp(7));
        badge.setBackground(cardBackground(Color.argb(50, 255, 255, 255), Color.TRANSPARENT, 18));
        return badge;
    }

    private TextView actionButton(String label, int textColor, int fill, int stroke) {
        TextView button = text(label, 15, textColor, Typeface.BOLD);
        button.setGravity(Gravity.CENTER);
        button.setPadding(dp(14), 0, dp(14), 0);
        button.setBackground(cardBackground(fill, stroke, 8));
        button.setClickable(true);
        return button;
    }

    private LinearLayout labeledInput(String label, EditText input) {
        LinearLayout field = column();
        TextView labelView = text(label, 13, COLOR_MUTED, Typeface.BOLD);
        labelView.setGravity(Gravity.RIGHT);
        field.addView(labelView, matchWrap());
        field.addView(input, margin(matchHeight(dp(52)), 0, dp(5), 0, 0));
        return field;
    }

    private EditText input(String hint) {
        EditText editText = new EditText(this);
        editText.setHint(hint);
        editText.setSingleLine(true);
        editText.setTextSize(16);
        editText.setTextColor(COLOR_INK);
        editText.setHintTextColor(COLOR_MUTED);
        editText.setGravity(Gravity.RIGHT | Gravity.CENTER_VERTICAL);
        editText.setTextDirection(View.TEXT_DIRECTION_RTL);
        editText.setPadding(dp(14), 0, dp(14), 0);
        editText.setMinHeight(dp(52));
        editText.setBackground(cardBackground(Color.WHITE, Color.rgb(203, 213, 225), 8));
        return editText;
    }

    private Button primaryButton(String label) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextColor(Color.WHITE);
        button.setTextSize(16);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setBackground(cardBackground(COLOR_TEAL, COLOR_TEAL, 8));
        return button;
    }

    private Button secondaryButton(String label) {
        Button button = new Button(this);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextColor(COLOR_INK);
        button.setTextSize(14);
        button.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        button.setBackground(cardBackground(Color.WHITE, Color.rgb(203, 213, 225), 8));
        return button;
    }

    private Button ghostButton(String label) {
        Button button = secondaryButton(label);
        button.setTextColor(COLOR_MUTED);
        return button;
    }

    private GradientDrawable cardBackground(int fill, int stroke, int radiusDp) {
        GradientDrawable drawable = new GradientDrawable();
        drawable.setColor(fill);
        drawable.setCornerRadius(dp(radiusDp));
        if (stroke != Color.TRANSPARENT) {
            drawable.setStroke(dp(1), stroke);
        }
        return drawable;
    }

    private int colorWithAlpha(int color, int alpha) {
        return Color.argb(alpha, Color.red(color), Color.green(color), Color.blue(color));
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private LinearLayout.LayoutParams matchHeight(int height) {
        return new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            height
        );
    }

    private LinearLayout.LayoutParams widthHeight(int width, int height) {
        return new LinearLayout.LayoutParams(width, height);
    }

    private LinearLayout.LayoutParams weightWrap(float weight) {
        return new LinearLayout.LayoutParams(0, LinearLayout.LayoutParams.WRAP_CONTENT, weight);
    }

    private LinearLayout.LayoutParams weightHeight(float weight, int height) {
        return new LinearLayout.LayoutParams(0, height, weight);
    }

    private LinearLayout.LayoutParams margin(LinearLayout.LayoutParams params, int left, int top, int right, int bottom) {
        params.setMargins(left, top, right, bottom);
        return params;
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(value * density);
    }

    @Override
    protected void onDestroy() {
        executor.shutdownNow();
        super.onDestroy();
    }

    private static class ApiException extends Exception {
        final int statusCode;
        final String response;

        ApiException(int statusCode, String response) {
            super("HTTP " + statusCode);
            this.statusCode = statusCode;
            this.response = response == null ? "" : response;
        }

        String detail() {
            try {
                JSONObject json = new JSONObject(response);
                Object detail = json.opt("detail");
                return detail == null ? "" : String.valueOf(detail);
            } catch (Exception ignored) {
                return response;
            }
        }
    }

    private static class AtmItem {
        final String atmId;
        final String name;
        final String branch;
        final String vpnIp;
        final String status;
        final boolean isOnline;
        final String agentVersion;
        final int latencyMs;
        final String cashStatus;

        AtmItem(String atmId, String name, String branch, String vpnIp, String status, boolean isOnline, String agentVersion, int latencyMs, String cashStatus) {
            this.atmId = atmId;
            this.name = name;
            this.branch = branch;
            this.vpnIp = vpnIp;
            this.status = status;
            this.isOnline = isOnline;
            this.agentVersion = agentVersion;
            this.latencyMs = latencyMs;
            this.cashStatus = cashStatus;
        }
    }

    private static class CashSummary {
        final int cashLowAtms;
        final int cashEmptyAtms;
        final int cashCriticalAtms;
        final int openAlerts;

        CashSummary(int cashLowAtms, int cashEmptyAtms, int cashCriticalAtms, int openAlerts) {
            this.cashLowAtms = cashLowAtms;
            this.cashEmptyAtms = cashEmptyAtms;
            this.cashCriticalAtms = cashCriticalAtms;
            this.openAlerts = openAlerts;
        }
    }

    private static class CashDetails {
        final List<CashUnit> units = new ArrayList<>();
        RejectRetract rejectRetract;
    }

    private static class RejectRetract {
        final int rejectCount;
        final int retractCount;
        final int rejectMaxCapacity;
        final int retractMaxCapacity;

        RejectRetract(int rejectCount, int retractCount, int rejectMaxCapacity, int retractMaxCapacity) {
            this.rejectCount = rejectCount;
            this.retractCount = retractCount;
            this.rejectMaxCapacity = rejectMaxCapacity;
            this.retractMaxCapacity = retractMaxCapacity;
        }
    }

    private static class CashUnit {
        final int cassetteNo;
        final String expectedCurrency;
        final int expectedDenomination;
        final int currentCount;
        final int rejectCount;
        final int lowThreshold;
        final int criticalThreshold;
        final int maxCapacity;
        final String status;
        final String readAt;

        CashUnit(int cassetteNo, String expectedCurrency, int expectedDenomination, int currentCount, int rejectCount, int lowThreshold, int criticalThreshold, int maxCapacity, String status, String readAt) {
            this.cassetteNo = cassetteNo;
            this.expectedCurrency = expectedCurrency;
            this.expectedDenomination = expectedDenomination;
            this.currentCount = currentCount;
            this.rejectCount = rejectCount;
            this.lowThreshold = lowThreshold;
            this.criticalThreshold = criticalThreshold;
            this.maxCapacity = maxCapacity;
            this.status = status;
            this.readAt = readAt;
        }
    }

    private static class CashUnitTone {
        final String label;
        final int color;
        final int fill;

        CashUnitTone(String label, int color, int fill) {
            this.label = label;
            this.color = color;
            this.fill = fill;
        }
    }
}
