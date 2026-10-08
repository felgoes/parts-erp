package br.com.goesautoparts.erp;

import android.app.NotificationChannel;
import android.app.NotificationChannelGroup;
import android.app.NotificationManager;
import android.content.Context;
import android.media.AudioAttributes;
import android.media.RingtoneManager;
import android.net.Uri;
import android.os.Build;
import androidx.core.app.NotificationCompat;
import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

public class PartsFirebaseMessagingService extends FirebaseMessagingService {
    private static final String LEGACY_CHANNEL_ID = "sales";
    private static final String[] CATEGORIES = {"sales", "order_status", "fiscal", "backup", "system"};
    private static final String[] CATEGORY_LABELS = {"Novas vendas", "Status dos pedidos", "Notas e etiquetas", "Backups", "Sistema"};
    private static final String[] SOUNDS = {"bell", "chime", "soft", "silent"};
    private static final String[] SOUND_LABELS = {"Sino", "Toque", "Suave", "Silencioso"};

    private static String channelId(String category, String sound) {
        return "parts_v1_" + category + "_" + sound;
    }

    public static void createNotificationChannels(Context context) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return;
        NotificationManager manager = context.getSystemService(NotificationManager.class);
        manager.createNotificationChannel(new NotificationChannel(
            LEGACY_CHANNEL_ID, "Vendas", NotificationManager.IMPORTANCE_HIGH
        ));
        AudioAttributes attributes = new AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_NOTIFICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SONIFICATION)
            .build();
        for (int categoryIndex = 0; categoryIndex < CATEGORIES.length; categoryIndex++) {
            String category = CATEGORIES[categoryIndex];
            manager.createNotificationChannelGroup(new NotificationChannelGroup(
                "parts_v1_" + category, CATEGORY_LABELS[categoryIndex]
            ));
            for (int soundIndex = 0; soundIndex < SOUNDS.length; soundIndex++) {
                String sound = SOUNDS[soundIndex];
                NotificationChannel channel = new NotificationChannel(
                    channelId(category, sound),
                    CATEGORY_LABELS[categoryIndex] + " · " + SOUND_LABELS[soundIndex],
                    NotificationManager.IMPORTANCE_HIGH
                );
                channel.setGroup("parts_v1_" + category);
                if ("silent".equals(sound)) channel.setSound(null, null);
                else {
                    int resource = context.getResources().getIdentifier(
                        "notification_" + sound, "raw", context.getPackageName()
                    );
                    Uri soundUri = resource != 0
                        ? Uri.parse("android.resource://" + context.getPackageName() + "/" + resource)
                        : RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION);
                    channel.setSound(soundUri, attributes);
                }
                manager.createNotificationChannel(channel);
            }
        }
    }

    @Override
    public void onMessageReceived(RemoteMessage message) {
        RemoteMessage.Notification remote = message.getNotification();
        if (remote == null) return;
        createNotificationChannels(this);
        String channel = message.getData().get("notification_channel");
        if (channel == null || channel.isEmpty()) channel = LEGACY_CHANNEL_ID;
        NotificationCompat.Builder builder = new NotificationCompat.Builder(this, channel)
            .setSmallIcon(R.mipmap.ic_launcher)
            .setContentTitle(remote.getTitle())
            .setContentText(remote.getBody())
            .setAutoCancel(true)
            .setPriority(NotificationCompat.PRIORITY_HIGH);
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) {
            String sound = message.getData().get("notification_sound");
            if ("silent".equals(sound)) builder.setSound(null);
            else if ("system".equals(sound) || sound == null || sound.isEmpty())
                builder.setSound(RingtoneManager.getDefaultUri(RingtoneManager.TYPE_NOTIFICATION));
            else {
                int resource = getResources().getIdentifier("notification_" + sound, "raw", getPackageName());
                if (resource != 0) builder.setSound(Uri.parse("android.resource://" + getPackageName() + "/" + resource));
            }
        }
        NotificationManager manager = getSystemService(NotificationManager.class);
        manager.notify((int) System.currentTimeMillis(), builder.build());
    }
}
