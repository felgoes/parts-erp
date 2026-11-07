package br.com.goesautoparts.erp;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import androidx.core.app.ActivityCompat;
import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import com.google.firebase.messaging.FirebaseMessaging;

@CapacitorPlugin(name = "PushNotifications")
public class PushNotificationsPlugin extends Plugin {
    private static final int NOTIFICATION_PERMISSION_REQUEST = 991;

    private static final String[] OPEN_FIELDS = {
        "parts_event_id", "type", "route", "invoice_id", "marketplace_order_id"
    };

    private JSObject readLaunch(Intent intent) {
        JSObject data = new JSObject();
        if (intent == null || !intent.hasExtra("parts_event_id")) return data;
        for (String field : OPEN_FIELDS) {
            String value = intent.getStringExtra(field);
            if (value != null) data.put(field, value);
            intent.removeExtra(field);
        }
        return data;
    }

    @PluginMethod
    public void takeLaunch(PluginCall call) {
        call.resolve(readLaunch(getActivity().getIntent()));
    }

    @Override
    protected void handleOnNewIntent(Intent intent) {
        JSObject data = readLaunch(intent);
        if (data.has("parts_event_id")) notifyListeners("notificationOpened", data, true);
    }

    @PluginMethod
    public void register(PluginCall call) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU
            && ActivityCompat.checkSelfPermission(getContext(), Manifest.permission.POST_NOTIFICATIONS)
                != PackageManager.PERMISSION_GRANTED) {
            ActivityCompat.requestPermissions(
                getActivity(), new String[] { Manifest.permission.POST_NOTIFICATIONS },
                NOTIFICATION_PERMISSION_REQUEST
            );
        }
        try {
            FirebaseMessaging.getInstance().getToken()
                .addOnSuccessListener(token -> {
                    JSObject result = new JSObject();
                    result.put("token", token);
                    call.resolve(result);
                })
                .addOnFailureListener(error -> call.reject(
                    "Não foi possível ativar as notificações", error
                ));
        } catch (Exception error) {
            call.reject("As notificações ainda não foram configuradas neste aplicativo", error);
        }
    }
}
