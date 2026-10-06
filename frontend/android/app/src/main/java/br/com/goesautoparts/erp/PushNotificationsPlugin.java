package br.com.goesautoparts.erp;

import android.Manifest;
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
