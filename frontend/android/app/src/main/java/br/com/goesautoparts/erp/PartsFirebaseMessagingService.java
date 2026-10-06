package br.com.goesautoparts.erp;

import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

public class PartsFirebaseMessagingService extends FirebaseMessagingService {
    private static final String CHANNEL_ID = "sales";

    @Override
    public void onMessageReceived(RemoteMessage message) {
        RemoteMessage.Notification remote = message.getNotification();
        if (remote == null) return;
        NotificationManager manager = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(new NotificationChannel(
                CHANNEL_ID, "Vendas", NotificationManager.IMPORTANCE_HIGH
            ));
        }
        manager.notify((int) System.currentTimeMillis(), new NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(remote.getTitle())
            .setContentText(remote.getBody())
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH)
            .build());
    }
}
