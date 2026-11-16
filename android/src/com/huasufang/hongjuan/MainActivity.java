package com.huasufang.hongjuan;

import android.app.Activity;
import android.net.Uri;
import android.os.Bundle;
import android.view.View;
import android.webkit.JavascriptInterface;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.ByteArrayInputStream;
import java.io.IOException;
import java.io.InputStream;

/**
 * 一个 WebView 壳：页面还是 web/ 里那套，数据走本地 SQLite。
 * 32 位以上的系统已经不许 file:// 页面读别的 file:// 资源，
 * 所以页面和图片统一走 https://app.local/，由 shouldInterceptRequest 从 assets 里取。
 */
public class MainActivity extends Activity {

    static final String HOST = "app.local";
    static final String HOME = "https://" + HOST + "/www/index.html";

    private WebView web;
    private Db db;

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        db = new Db(this);
        db.ensure();

        web = new WebView(this);
        WebView.setWebContentsDebuggingEnabled(true);
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);
        s.setTextZoom(100);
        s.setUseWideViewPort(false);
        s.setLoadWithOverviewMode(false);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        web.setBackgroundColor(0xFFF4EFE5);
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        web.setWebViewClient(new WebViewClient() {
            @Override
            public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest req) {
                Uri u = req.getUrl();
                if (u == null || !HOST.equals(u.getHost())) return null;
                String path = u.getPath();
                if (path == null || path.equals("/")) path = "/www/index.html";
                if (path.startsWith("/")) path = path.substring(1);
                try {
                    InputStream in = getAssets().open(path);
                    String mime = mimeOf(path);
                    String enc = (mime.startsWith("text/") || mime.contains("javascript")) ? "utf-8" : null;
                    return new WebResourceResponse(mime, enc, in);
                } catch (IOException e) {
                    return new WebResourceResponse("text/plain", "utf-8",
                            new ByteArrayInputStream(new byte[0]));
                }
            }
        });
        web.addJavascriptInterface(new Bridge(), "HJNative");
        web.loadUrl(HOME);
        setContentView(web);
    }

    private static String mimeOf(String path) {
        String p = path.toLowerCase();
        if (p.endsWith(".html")) return "text/html";
        if (p.endsWith(".js")) return "application/javascript";
        if (p.endsWith(".css")) return "text/css";
        if (p.endsWith(".webp")) return "image/webp";
        if (p.endsWith(".png")) return "image/png";
        if (p.endsWith(".jpg") || p.endsWith(".jpeg")) return "image/jpeg";
        if (p.endsWith(".gif")) return "image/gif";
        if (p.endsWith(".svg")) return "image/svg+xml";
        return "application/octet-stream";
    }

    public class Bridge {
        @JavascriptInterface
        public String call(String path, String body) {
            return db.handle(path, body);
        }
    }

    // 返回键：在子页面就回今日，在今日就退出
    @Override
    public void onBackPressed() {
        web.evaluateJavascript("(location.hash||'#/')", new android.webkit.ValueCallback<String>() {
            @Override
            public void onReceiveValue(String v) {
                if (v != null && (v.equals("\"#/\"") || v.equals("\"#\"") || v.equals("\"\""))) {
                    finish();
                } else {
                    web.evaluateJavascript("location.hash='#/'", null);
                }
            }
        });
    }
}
