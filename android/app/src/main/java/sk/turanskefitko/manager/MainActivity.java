package sk.turanskefitko.manager;

import android.Manifest;
import android.annotation.SuppressLint;
import android.app.Activity;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.HashMap;
import java.util.Map;

import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

public class MainActivity extends Activity {
    private static final String APP_URL = "https://turanskefitko.sk/tfm-app/?native=android";
    private static final String APP_HOST = "turanskefitko.sk";
    private static final String APP_PATH_PREFIX = "/tfm-app/";
    private static final String AUTH_HEADER = "X-TFMA-Device-Pass";

    private WebView webView;
    private SecureDevicePassStore devicePassStore;

    @SuppressLint({"SetJavaScriptEnabled", "AddJavascriptInterface"})
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        devicePassStore = new SecureDevicePassStore(this);

        getWindow().setStatusBarColor(Color.rgb(5, 7, 5));
        getWindow().setNavigationBarColor(Color.rgb(5, 7, 5));

        webView = new WebView(this);
        webView.setLayoutParams(new FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
        ));
        setContentView(webView);

        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setDatabaseEnabled(true);
        settings.setLoadWithOverviewMode(true);
        settings.setUseWideViewPort(true);
        settings.setSupportZoom(false);
        settings.setBuiltInZoomControls(false);
        settings.setDisplayZoomControls(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setUserAgentString(settings.getUserAgentString()
                + " TFMAndroidApp/5.0 TuranskeFitko/AppLinks NativeDevicePass/1");

        // Server may only CALL these two methods after it has already authenticated
        // the user on turanskefitko.sk. The secret never needs to be exposed back to JS.
        webView.addJavascriptInterface(new NativeAuthBridge(), "TFMNativeAuth");

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.LOLLIPOP) {
            cookies.setAcceptThirdPartyCookies(webView, true);
        }

        webView.setWebChromeClient(new WebChromeClient());
        webView.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return handleUrl(request.getUrl().toString());
            }

            @Override
            public boolean shouldOverrideUrlLoading(WebView view, String url) {
                return handleUrl(url);
            }

            @Override
            public void onPageFinished(WebView view, String url) {
                super.onPageFinished(view, url);
                CookieManager.getInstance().flush();
            }
        });

        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 10);
        }

        openFromIntentOrHome(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        openFromIntentOrHome(intent);
    }

    @Override
    protected void onPause() {
        CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override
    protected void onStop() {
        CookieManager.getInstance().flush();
        super.onStop();
    }

    private void openFromIntentOrHome(Intent intent) {
        Uri data = intent != null ? intent.getData() : null;
        if (isAppLink(data)) {
            // The exact same NFC/passwordless HTTPS URL is preserved. A securely stored
            // Device Pass is attached only as a request header, never in the URL/history.
            loadFirstPartyWithNativeAuth(data.toString());
        } else if (webView.getUrl() == null || webView.getUrl().isEmpty()) {
            // Cold app start also gets the header. Thus a lost WordPress cookie can be
            // reconstructed before the home page is rendered.
            loadFirstPartyWithNativeAuth(APP_URL);
        }
    }

    private void loadFirstPartyWithNativeAuth(String url) {
        String pass = devicePassStore.get();
        if (pass == null || pass.isEmpty()) {
            webView.loadUrl(url);
            return;
        }
        Map<String, String> headers = new HashMap<>();
        headers.put(AUTH_HEADER, pass);
        headers.put("X-TFMA-Android-Native", "5.0");
        webView.loadUrl(url, headers);
    }

    private boolean isAppLink(Uri uri) {
        if (uri == null) return false;
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();
        String path = uri.getPath() == null ? "" : uri.getPath();
        return "https".equals(scheme)
                && APP_HOST.equals(host)
                && path.startsWith(APP_PATH_PREFIX);
    }

    private boolean handleUrl(String url) {
        if (url == null) return false;
        Uri uri = Uri.parse(url);
        String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
        String host = uri.getHost() == null ? "" : uri.getHost().toLowerCase();

        if (scheme.equals("https") && (host.equals(APP_HOST) || host.equals("www." + APP_HOST))) {
            // Explicit logout/account removal is authoritative and must also erase the
            // encrypted native credential, otherwise the next cold start would log in again.
            if (url.contains("tfma61_logout=1")
                    || url.contains("tfma_logout_complete=1")
                    || url.contains("tfma_account_deleted=1")) {
                devicePassStore.clear();
            }
            return false;
        }

        if (scheme.equals("tel") || scheme.equals("mailto") || scheme.equals("sms")
                || scheme.equals("whatsapp") || scheme.equals("intent")) {
            try {
                startActivity(new Intent(Intent.ACTION_VIEW, uri));
                return true;
            } catch (Exception ignored) {
                return true;
            }
        }
        return false;
    }

    private final class NativeAuthBridge {
        @JavascriptInterface
        public void saveDevicePass(String value) {
            if (isValidDevicePass(value)) {
                devicePassStore.put(value);
            }
        }

        @JavascriptInterface
        public void clearDevicePass() {
            devicePassStore.clear();
        }
    }

    private boolean isValidDevicePass(String value) {
        if (value == null || value.length() < 52 || value.length() > 180) return false;
        int dot = value.indexOf('.');
        if (dot <= 0 || dot >= value.length() - 1) return false;
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            if (c == '.') continue;
            if ((c >= '0' && c <= '9') || (c >= 'A' && c <= 'Z')
                    || (c >= 'a' && c <= 'z') || c == '_' || c == '-') continue;
            return false;
        }
        return true;
    }

    private static final class SecureDevicePassStore {
        private static final String PREFS = "tfm_native_auth_v1";
        private static final String PREF_IV = "device_pass_iv";
        private static final String PREF_DATA = "device_pass_data";
        private static final String KEY_ALIAS = "tfm_device_pass_aes_v1";

        private final SharedPreferences prefs;

        SecureDevicePassStore(Context context) {
            prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        }

        synchronized void put(String value) {
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
                byte[] encrypted = cipher.doFinal(value.getBytes(StandardCharsets.UTF_8));
                prefs.edit()
                        .putString(PREF_IV, Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
                        .putString(PREF_DATA, Base64.encodeToString(encrypted, Base64.NO_WRAP))
                        .apply();
            } catch (Exception error) {
                clear();
            }
        }

        synchronized String get() {
            String ivText = prefs.getString(PREF_IV, "");
            String dataText = prefs.getString(PREF_DATA, "");
            if (ivText == null || dataText == null || ivText.isEmpty() || dataText.isEmpty()) return "";
            try {
                byte[] iv = Base64.decode(ivText, Base64.NO_WRAP);
                byte[] encrypted = Base64.decode(dataText, Base64.NO_WRAP);
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), new GCMParameterSpec(128, iv));
                byte[] plain = cipher.doFinal(encrypted);
                return new String(plain, StandardCharsets.UTF_8);
            } catch (Exception error) {
                clear();
                return "";
            }
        }

        synchronized void clear() {
            prefs.edit().remove(PREF_IV).remove(PREF_DATA).apply();
        }

        private SecretKey getOrCreateKey() throws Exception {
            KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore");
            keyStore.load(null);
            if (keyStore.containsAlias(KEY_ALIAS)) {
                return ((KeyStore.SecretKeyEntry) keyStore.getEntry(KEY_ALIAS, null)).getSecretKey();
            }

            KeyGenerator generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore");
            KeyGenParameterSpec spec = new KeyGenParameterSpec.Builder(
                    KEY_ALIAS,
                    KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT
            )
                    .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                    .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                    .setRandomizedEncryptionRequired(true)
                    .build();
            generator.init(spec);
            return generator.generateKey();
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) {
            webView.goBack();
        } else {
            super.onBackPressed();
        }
    }
}
