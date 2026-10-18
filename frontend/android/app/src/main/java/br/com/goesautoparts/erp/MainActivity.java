package br.com.goesautoparts.erp;

import android.os.Bundle;
import android.view.ViewGroup;
import android.webkit.WebView;
import androidx.activity.OnBackPressedCallback;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowInsetsCompat;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(BiometricLoginPlugin.class);
        registerPlugin(PushNotificationsPlugin.class);
        registerPlugin(DocumentOpenerPlugin.class);
        super.onCreate(savedInstanceState);
        PartsFirebaseMessagingService.createNotificationChannels(this);
        if (bridge != null && bridge.getWebView() != null) {
            bridge.getWebView().post(this::applyKeyboardInsets);
        }
        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                if (bridge != null && bridge.getWebView() != null && bridge.getWebView().canGoBack()) {
                    bridge.getWebView().goBack();
                    return;
                }
                setEnabled(false);
                getOnBackPressedDispatcher().onBackPressed();
            }
        });
    }

    @Override
    public void onResume() {
        super.onResume();
        applyKeyboardInsets();
    }

    /**
     * O WebView do Capacitor consome os insets de sistema e não trata o teclado. Sem esta
     * margem, o Android 15 mantém o conteúdo atrás do IME mesmo com adjustResize.
     */
    private void applyKeyboardInsets() {
        if (bridge == null || bridge.getWebView() == null) return;
        WebView webView = bridge.getWebView();
        ViewCompat.setOnApplyWindowInsetsListener(webView, (view, windowInsets) -> {
            Insets bars = windowInsets.getInsets(
                WindowInsetsCompat.Type.systemBars() | WindowInsetsCompat.Type.displayCutout()
            );
            Insets keyboard = windowInsets.getInsets(WindowInsetsCompat.Type.ime());
            ViewGroup.MarginLayoutParams params =
                (ViewGroup.MarginLayoutParams) view.getLayoutParams();
            params.leftMargin = bars.left;
            params.rightMargin = bars.right;
            params.topMargin = bars.top;
            params.bottomMargin = Math.max(bars.bottom, keyboard.bottom);
            view.setLayoutParams(params);
            return WindowInsetsCompat.CONSUMED;
        });
        ViewCompat.requestApplyInsets(webView);
    }
}
