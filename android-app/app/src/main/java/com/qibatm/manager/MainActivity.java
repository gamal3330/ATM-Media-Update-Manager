package com.qibatm.manager;

import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.View;
import android.webkit.ConsoleMessage;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.TextView;

public class MainActivity extends Activity {
    private static final int LOAD_TIMEOUT_MS = 12000;

    private WebView webView;
    private ProgressBar progressBar;
    private LinearLayout statusPanel;
    private TextView statusTitle;
    private TextView statusMessage;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private boolean pageVisible = false;

    private final Runnable loadTimeout = new Runnable() {
        @Override
        public void run() {
            if (!pageVisible) {
                showConnectionError("انتهت مهلة فتح الصفحة.");
            }
        }
    };

    @Override
    @SuppressLint("SetJavaScriptEnabled")
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        FrameLayout root = new FrameLayout(this);
        webView = new WebView(this);
        webView.setBackgroundColor(Color.WHITE);
        progressBar = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        statusPanel = new LinearLayout(this);
        statusTitle = new TextView(this);
        statusMessage = new TextView(this);

        root.addView(webView, new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));

        FrameLayout.LayoutParams progressParams = new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            dp(3)
        );
        progressParams.gravity = Gravity.TOP;
        root.addView(progressBar, progressParams);

        root.addView(buildStatusPanel(), new FrameLayout.LayoutParams(
            FrameLayout.LayoutParams.MATCH_PARENT,
            FrameLayout.LayoutParams.MATCH_PARENT
        ));

        setContentView(root);
        configureWebView();
        loadHome();
    }

    private View buildStatusPanel() {
        statusPanel.setOrientation(LinearLayout.VERTICAL);
        statusPanel.setGravity(Gravity.CENTER);
        statusPanel.setPadding(dp(28), dp(28), dp(28), dp(28));
        statusPanel.setBackgroundColor(Color.rgb(248, 250, 252));

        statusTitle.setGravity(Gravity.CENTER);
        statusTitle.setTextColor(Color.rgb(15, 23, 42));
        statusTitle.setTextSize(22);
        statusTitle.setTypeface(android.graphics.Typeface.DEFAULT_BOLD);

        statusMessage.setGravity(Gravity.CENTER);
        statusMessage.setTextColor(Color.rgb(71, 85, 105));
        statusMessage.setTextSize(15);
        statusMessage.setLineSpacing(0, 1.15f);
        LinearLayout.LayoutParams messageParams = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
        messageParams.setMargins(0, dp(12), 0, dp(18));

        Button retryButton = new Button(this);
        retryButton.setText("إعادة المحاولة");
        retryButton.setOnClickListener(view -> loadHome());

        Button browserButton = new Button(this);
        browserButton.setText("فتح في المتصفح");
        browserButton.setOnClickListener(view -> {
            Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(BuildConfig.SERVER_URL));
            startActivity(intent);
        });

        LinearLayout.LayoutParams buttonParams = new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            dp(48)
        );
        buttonParams.setMargins(0, dp(8), 0, 0);

        statusPanel.addView(statusTitle);
        statusPanel.addView(statusMessage, messageParams);
        statusPanel.addView(retryButton, buttonParams);
        statusPanel.addView(browserButton, buttonParams);
        return statusPanel;
    }

    private void configureWebView() {
        if (BuildConfig.DEBUG) {
            WebView.setWebContentsDebuggingEnabled(true);
        }

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setCacheMode(WebSettings.LOAD_NO_CACHE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            settings.setMixedContentMode(WebSettings.MIXED_CONTENT_ALWAYS_ALLOW);
        }

        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public void onProgressChanged(WebView view, int newProgress) {
                progressBar.setProgress(newProgress);
                progressBar.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
            }

            @Override
            public boolean onConsoleMessage(ConsoleMessage consoleMessage) {
                return super.onConsoleMessage(consoleMessage);
            }
        });

        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                view.loadUrl(request.getUrl().toString());
                return true;
            }

            @Override
            @SuppressWarnings("deprecation")
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                view.loadUrl(url);
                return true;
            }

            @Override
            public void onPageStarted(WebView view, String url, android.graphics.Bitmap favicon) {
                pageVisible = false;
                showLoading();
            }

            @Override
            public void onPageCommitVisible(WebView view, String url) {
                pageVisible = true;
                handler.removeCallbacks(loadTimeout);
                statusPanel.setVisibility(View.GONE);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                progressBar.setVisibility(View.GONE);
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
                if (request != null && request.isForMainFrame()) {
                    String description = Build.VERSION.SDK_INT >= Build.VERSION_CODES.M ? String.valueOf(error.getDescription()) : "خطأ اتصال";
                    showConnectionError(description);
                }
            }

            @Override
            @SuppressWarnings("deprecation")
            public void onReceivedError(WebView view, int errorCode, String description, String failingUrl) {
                showConnectionError(description);
            }

            @Override
            public void onReceivedHttpError(WebView view, WebResourceRequest request, WebResourceResponse errorResponse) {
                if (request != null && request.isForMainFrame()) {
                    showConnectionError("HTTP " + errorResponse.getStatusCode() + " " + errorResponse.getReasonPhrase());
                }
            }
        });
    }

    private void loadHome() {
        pageVisible = false;
        showLoading();
        webView.loadUrl(BuildConfig.SERVER_URL);
        handler.removeCallbacks(loadTimeout);
        handler.postDelayed(loadTimeout, LOAD_TIMEOUT_MS);
    }

    private void showLoading() {
        progressBar.setVisibility(View.VISIBLE);
        statusTitle.setText("جاري فتح QIB ATM Manager");
        statusMessage.setText("يتم الاتصال بالسيرفر:\n" + BuildConfig.SERVER_URL);
        statusPanel.setVisibility(View.VISIBLE);
    }

    private void showConnectionError(String details) {
        handler.removeCallbacks(loadTimeout);
        progressBar.setVisibility(View.GONE);
        statusTitle.setText("تعذر فتح النظام");
        statusMessage.setText(
            "تأكد أن جهاز Android متصل بنفس الشبكة أو VPN، وأن السيرفر يعمل ويمكن فتحه من المتصفح.\n\n"
                + BuildConfig.SERVER_URL
                + "\n\nالتفاصيل: "
                + details
        );
        statusPanel.setVisibility(View.VISIBLE);
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
            return;
        }
        super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        handler.removeCallbacks(loadTimeout);
        if (webView != null) {
            webView.destroy();
        }
        super.onDestroy();
    }

    private int dp(int value) {
        float density = getResources().getDisplayMetrics().density;
        return Math.round(value * density);
    }
}
