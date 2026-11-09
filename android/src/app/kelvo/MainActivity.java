package app.kelvo;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.text.InputType;
import android.util.Base64;
import android.util.TypedValue;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.EditorInfo;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.io.OutputStream;

/**
 * Kelvo for Android. Kelvo itself runs on your own server; this app shows it full-screen.
 * First launch asks for the server address (e.g. https://my-pc.my-tailnet.ts.net) and keeps it.
 */
public class MainActivity extends Activity {
    private static final String PREFS = "kelvo";
    private static final String KEY_URL = "server_url";
    private static final int REQ_FILE_CHOOSER = 1;
    private static final int REQ_SAVE_FILE = 2;
    private static final int ACCENT = 0xFF0B7C70;
    private static final int INK = 0xFF121821;
    private static final int MUTED = 0xFF4A5565;
    private static final int DANGER = 0xFFC0302F;
    private static final int BG = 0xFFF6F7F9;

    private WebView web;
    private String serverUrl;
    private ValueCallback<Uri[]> fileCallback;
    private byte[] pendingSave;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(ACCENT);
        serverUrl = prefs().getString(KEY_URL, null);
        if (serverUrl == null) showSetup(null);
        else showWeb();
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private int dp(int v) {
        return (int) TypedValue.applyDimension(TypedValue.COMPLEX_UNIT_DIP, v, getResources().getDisplayMetrics());
    }

    // ------------------------------------------------------------------ native screens

    private LinearLayout screen() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(dp(24), dp(48), dp(24), dp(24));
        box.setBackgroundColor(BG);
        return box;
    }

    private TextView text(String s, int sizeSp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(TypedValue.COMPLEX_UNIT_SP, sizeSp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        t.setPadding(0, 0, 0, dp(12));
        return t;
    }

    private Button button(String label, boolean primary) {
        Button b = new Button(this);
        b.setText(label);
        b.setAllCaps(false);
        b.setTextSize(TypedValue.COMPLEX_UNIT_SP, 16);
        if (primary) {
            b.setTextColor(Color.WHITE);
            b.getBackground().setTint(ACCENT);
        }
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, dp(52));
        lp.topMargin = dp(8);
        b.setLayoutParams(lp);
        return b;
    }

    private void show(View content) {
        if (web != null) {
            web.stopLoading();
        }
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);
        scroll.addView(content);
        setContentView(scroll);
    }

    /** First run, or "Change server address". */
    private void showSetup(String error) {
        LinearLayout box = screen();
        box.addView(text("Kelvo", 30, INK, true));
        box.addView(text("Enter the address of your Kelvo server. Turn on Tailscale on this phone first.", 16, MUTED, false));
        final EditText input = new EditText(this);
        input.setSingleLine(true);
        input.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        input.setImeOptions(EditorInfo.IME_ACTION_GO);
        input.setHint("https://my-pc.my-tailnet.ts.net");
        input.setText(serverUrl != null ? serverUrl : "https://");
        input.setSelection(input.getText().length());
        box.addView(input);
        if (error != null) box.addView(text(error, 14, DANGER, false));
        box.addView(text("Example: https://my-pc.my-tailnet.ts.net (from `tailscale serve status` on your server).", 13, MUTED, false));
        Button go = button("Connect", true);
        box.addView(go);
        View.OnClickListener connect = new View.OnClickListener() {
            @Override public void onClick(View v) { saveUrl(input.getText().toString()); }
        };
        go.setOnClickListener(connect);
        input.setOnEditorActionListener(new TextView.OnEditorActionListener() {
            @Override public boolean onEditorAction(TextView v, int actionId, android.view.KeyEvent event) {
                saveUrl(input.getText().toString());
                return true;
            }
        });
        show(box);
    }

    private void saveUrl(String raw) {
        String s = raw.trim();
        while (s.endsWith("/")) s = s.substring(0, s.length() - 1);
        Uri u = Uri.parse(s);
        String scheme = u.getScheme();
        if (scheme == null || u.getHost() == null || u.getHost().isEmpty()
                || !(scheme.equals("https") || scheme.equals("http"))) {
            showSetup("That doesn't look like an address. It should start with https:// and include your server's name.");
            return;
        }
        serverUrl = s;
        prefs().edit().putString(KEY_URL, s).apply();
        showWeb();
    }

    private void showError(String detail) {
        LinearLayout box = screen();
        box.addView(text("Can't reach Kelvo", 26, INK, true));
        box.addView(text("Tried " + serverUrl + ".", 15, MUTED, false));
        box.addView(text("Check that Tailscale is on, and that Kelvo is running on your server.", 16, MUTED, false));
        if (detail != null) box.addView(text(detail, 13, MUTED, false));
        Button retry = button("Try again", true);
        retry.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { showWeb(); } });
        Button change = button("Change server address", false);
        change.setOnClickListener(new View.OnClickListener() { @Override public void onClick(View v) { showSetup(null); } });
        box.addView(retry);
        box.addView(change);
        show(box);
    }

    // ------------------------------------------------------------------ web view

    private void showWeb() {
        if (web == null) web = buildWebView();
        if (web.getParent() != null) ((ViewGroup) web.getParent()).removeView(web);
        setContentView(web);
        web.loadUrl(serverUrl + "/");
    }

    private boolean isOwnServer(Uri u) {
        Uri s = Uri.parse(serverUrl);
        return u.getHost() != null && u.getHost().equalsIgnoreCase(s.getHost()) && u.getPort() == s.getPort();
    }

    private WebView buildWebView() {
        WebView w = new WebView(this);
        w.setBackgroundColor(BG);
        WebSettings ws = w.getSettings();
        ws.setJavaScriptEnabled(true);
        ws.setDomStorageEnabled(true);
        ws.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        ws.setAllowFileAccess(false);
        ws.setAllowContentAccess(false);
        ws.setUserAgentString(ws.getUserAgentString() + " KelvoAndroid/0.1");
        CookieManager.getInstance().setAcceptCookie(true);

        w.addJavascriptInterface(new Bridge(), "KelvoAndroid");

        w.setWebViewClient(new WebViewClient() {
            // String form: Android's default for the newer (WebResourceRequest) form delegates here on every version.
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                Uri u = Uri.parse(url);
                if (isOwnServer(u)) return false;
                openExternally(u); // links to other sites open in your browser, not inside the app
                return true;
            }

            @Override
            public void onReceivedError(WebView view, WebResourceRequest req, WebResourceError err) {
                if (req.isForMainFrame()) showError(String.valueOf(err.getDescription()));
            }

            @Override
            public void onReceivedSslError(WebView view, android.webkit.SslErrorHandler handler, android.net.http.SslError error) {
                handler.cancel(); // never accept a bad certificate
                showError("The server's HTTPS certificate isn't valid for this address.");
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                CookieManager.getInstance().flush(); // keep you signed in after the app is closed
            }
        });

        w.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileCallback != null) fileCallback.onReceiveValue(null);
                fileCallback = callback;
                try {
                    startActivityForResult(params.createIntent(), REQ_FILE_CHOOSER);
                } catch (ActivityNotFoundException e) {
                    fileCallback = null;
                    return false;
                }
                return true;
            }
        });

        // Exports (flow JSON, SKILL.md) are blob: downloads; read them in the page and save via the system file picker.
        w.setDownloadListener(new android.webkit.DownloadListener() { @Override public void onDownloadStart(String url, String userAgent, String contentDisposition, String mimetype, long length) {
            if (url.startsWith("blob:")) {
                String name = URLUtil.guessFileName(url, contentDisposition, mimetype);
                String js = "(async()=>{try{const b=await (await fetch(" + jsString(url) + ")).blob();"
                        + "const a=[...document.querySelectorAll('a[download]')].pop();"
                        + "const n=(a&&a.download)||" + jsString(name) + ";"
                        + "const r=new FileReader();r.onload=()=>KelvoAndroid.save(String(r.result).split(',')[1],n,b.type||'application/octet-stream');"
                        + "r.readAsDataURL(b);}catch(e){KelvoAndroid.toast('Export failed: '+e)}})()";
                web.evaluateJavascript(js, null);
            } else {
                openExternally(Uri.parse(url));
            }
        }});
        return w;
    }

    private static String jsString(String s) {
        return "'" + s.replace("\\", "\\\\").replace("'", "\\'") + "'";
    }

    private void openExternally(Uri u) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, u));
        } catch (ActivityNotFoundException e) {
            Toast.makeText(this, "No app can open " + u, Toast.LENGTH_SHORT).show();
        }
    }

    /** Called from Kelvo's web page. Only your own server is ever loaded in this WebView. */
    private class Bridge {
        @JavascriptInterface
        public void save(String base64, String filename, String mime) {
            pendingSave = Base64.decode(base64, Base64.DEFAULT);
            final Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
            i.addCategory(Intent.CATEGORY_OPENABLE);
            i.setType(mime == null || mime.isEmpty() ? "application/octet-stream" : mime);
            i.putExtra(Intent.EXTRA_TITLE, filename);
            runOnUiThread(new Runnable() { @Override public void run() { startActivityForResult(i, REQ_SAVE_FILE); } });
        }

        @JavascriptInterface
        public void toast(final String msg) {
            runOnUiThread(new Runnable() { @Override public void run() { Toast.makeText(MainActivity.this, msg, Toast.LENGTH_LONG).show(); } });
        }

        @JavascriptInterface
        public void changeServer() {
            runOnUiThread(new Runnable() { @Override public void run() {
                new AlertDialog.Builder(MainActivity.this)
                        .setTitle("Change server address?")
                        .setMessage("You're connected to " + serverUrl)
                        .setPositiveButton("Change", new android.content.DialogInterface.OnClickListener() {
                            @Override public void onClick(android.content.DialogInterface d, int which) { showSetup(null); }
                        })
                        .setNegativeButton("Cancel", null)
                        .show();
            } });
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode == REQ_FILE_CHOOSER) {
            if (fileCallback != null) {
                fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
                fileCallback = null;
            }
            return;
        }
        if (requestCode == REQ_SAVE_FILE) {
            byte[] bytes = pendingSave;
            pendingSave = null;
            if (resultCode != RESULT_OK || data == null || data.getData() == null || bytes == null) return;
            try (OutputStream out = getContentResolver().openOutputStream(data.getData())) {
                out.write(bytes);
                Toast.makeText(this, "Saved", Toast.LENGTH_SHORT).show();
            } catch (Exception e) {
                Toast.makeText(this, "Couldn't save: " + e.getMessage(), Toast.LENGTH_LONG).show();
            }
            return;
        }
        super.onActivityResult(requestCode, resultCode, data);
    }

    @Override
    public void onBackPressed() {
        if (web != null && web.getParent() != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }
}
