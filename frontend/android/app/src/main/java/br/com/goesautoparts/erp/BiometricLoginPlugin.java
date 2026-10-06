package br.com.goesautoparts.erp;

import android.content.Context;
import android.content.SharedPreferences;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import androidx.annotation.NonNull;
import androidx.biometric.BiometricManager;
import androidx.biometric.BiometricPrompt;
import androidx.core.content.ContextCompat;
import androidx.fragment.app.FragmentActivity;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.concurrent.Executor;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

@CapacitorPlugin(name = "BiometricLogin")
public class BiometricLoginPlugin extends Plugin {
    private static final String PREFS = "parts_erp_biometric";
    private static final String CREDENTIAL = "credential";
    private static final String IV = "iv";
    private static final String EMAIL = "email";
    private static final String KEY_ALIAS = "parts_erp_biometric_key";

    @PluginMethod
    public void status(PluginCall call) {
        int result = BiometricManager.from(getContext()).canAuthenticate(
            BiometricManager.Authenticators.BIOMETRIC_STRONG
        );
        SharedPreferences prefs = preferences();
        JSObject response = new JSObject();
        response.put("available", result == BiometricManager.BIOMETRIC_SUCCESS);
        response.put("configured", prefs.contains(CREDENTIAL) && prefs.contains(IV));
        response.put("email", prefs.getString(EMAIL, null));
        call.resolve(response);
    }

    @PluginMethod
    public void saveCredential(PluginCall call) {
        String credential = call.getString("credential");
        String email = call.getString("email");
        if (credential == null || credential.isBlank()) {
            call.reject("Credencial biométrica ausente");
            return;
        }
        showPrompt(call, "Ativar acesso com digital", "Confirme sua identidade", () -> {
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey());
                byte[] encrypted = cipher.doFinal(credential.getBytes(StandardCharsets.UTF_8));
                preferences().edit()
                    .putString(CREDENTIAL, Base64.encodeToString(encrypted, Base64.NO_WRAP))
                    .putString(IV, Base64.encodeToString(cipher.getIV(), Base64.NO_WRAP))
                    .putString(EMAIL, email)
                    .apply();
                call.resolve();
            } catch (Exception exception) {
                call.reject("Não foi possível proteger a credencial biométrica", exception);
            }
        });
    }

    @PluginMethod
    public void authenticate(PluginCall call) {
        if (!preferences().contains(CREDENTIAL)) {
            call.reject("A digital ainda não foi configurada", "NOT_CONFIGURED");
            return;
        }
        showPrompt(call, "Entrar no Parts ERP", "Use sua digital para continuar", () -> {
            try {
                Cipher cipher = Cipher.getInstance("AES/GCM/NoPadding");
                byte[] iv = Base64.decode(preferences().getString(IV, ""), Base64.NO_WRAP);
                cipher.init(Cipher.DECRYPT_MODE, getOrCreateKey(), new GCMParameterSpec(128, iv));
                byte[] encrypted = Base64.decode(
                    preferences().getString(CREDENTIAL, ""), Base64.NO_WRAP
                );
                String credential = new String(
                    cipher.doFinal(encrypted), StandardCharsets.UTF_8
                );
                JSObject response = new JSObject();
                response.put("credential", credential);
                response.put("email", preferences().getString(EMAIL, null));
                call.resolve(response);
            } catch (Exception exception) {
                clearStoredCredential();
                call.reject("A credencial biométrica precisa ser configurada novamente", exception);
            }
        });
    }

    @PluginMethod
    public void clearCredential(PluginCall call) {
        clearStoredCredential();
        call.resolve();
    }

    private void showPrompt(
        PluginCall call,
        String title,
        String subtitle,
        Runnable onSuccess
    ) {
        getActivity().runOnUiThread(() -> {
            if (!(getActivity() instanceof FragmentActivity activity)) {
                call.reject("Tela Android incompatível com autenticação biométrica");
                return;
            }
            Executor executor = ContextCompat.getMainExecutor(getContext());
            BiometricPrompt prompt = new BiometricPrompt(
                activity,
                executor,
                new BiometricPrompt.AuthenticationCallback() {
                    @Override
                    public void onAuthenticationError(int errorCode, @NonNull CharSequence errString) {
                        super.onAuthenticationError(errorCode, errString);
                        call.reject(errString.toString(), "BIOMETRIC_CANCELLED");
                    }

                    @Override
                    public void onAuthenticationSucceeded(
                        @NonNull BiometricPrompt.AuthenticationResult result
                    ) {
                        super.onAuthenticationSucceeded(result);
                        onSuccess.run();
                    }
                }
            );
            BiometricPrompt.PromptInfo promptInfo = new BiometricPrompt.PromptInfo.Builder()
                .setTitle(title)
                .setSubtitle(subtitle)
                .setNegativeButtonText("Cancelar")
                .setAllowedAuthenticators(BiometricManager.Authenticators.BIOMETRIC_STRONG)
                .build();
            prompt.authenticate(promptInfo);
        });
    }

    private SharedPreferences preferences() {
        return getContext().getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    private SecretKey getOrCreateKey() throws Exception {
        KeyStore keyStore = KeyStore.getInstance("AndroidKeyStore");
        keyStore.load(null);
        SecretKey existing = (SecretKey) keyStore.getKey(KEY_ALIAS, null);
        if (existing != null) return existing;

        KeyGenerator generator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore"
        );
        generator.init(
            new KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT | KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .build()
        );
        return generator.generateKey();
    }

    private void clearStoredCredential() {
        preferences().edit().clear().apply();
    }
}
