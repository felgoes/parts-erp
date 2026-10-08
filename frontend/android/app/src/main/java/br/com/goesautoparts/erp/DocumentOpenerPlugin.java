package br.com.goesautoparts.erp;

import android.content.Intent;
import android.content.ContentValues;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import androidx.core.content.FileProvider;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;
import java.io.File;
import java.io.FileOutputStream;

@CapacitorPlugin(name = "DocumentOpener")
public class DocumentOpenerPlugin extends Plugin {
    @PluginMethod
    public void openUrl(PluginCall call) {
        String url = call.getString("url");
        if (url == null || !(url.startsWith("https://") || url.startsWith("http://"))) {
            call.reject("Link de documento inválido");
            return;
        }
        Intent intent = new Intent(Intent.ACTION_VIEW, Uri.parse(url));
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        if (intent.resolveActivity(getContext().getPackageManager()) == null) {
            call.reject("Nenhum navegador encontrado no celular");
            return;
        }
        getContext().startActivity(intent);
        call.resolve();
    }

    @PluginMethod
    public void open(PluginCall call) {
        String encoded = call.getString("base64");
        String mimeType = call.getString("mimeType", "application/octet-stream");
        String fileName = call.getString("fileName", "documento");
        if (encoded == null || encoded.isBlank()) {
            call.reject("Conteúdo do documento ausente");
            return;
        }
        try {
            String safeName = fileName.replaceAll("[^a-zA-Z0-9._-]", "_");
            File file = new File(getContext().getCacheDir(), safeName);
            byte[] bytes = Base64.decode(encoded, Base64.DEFAULT);
            try (FileOutputStream output = new FileOutputStream(file)) {
                output.write(bytes);
            }
            Uri uri = FileProvider.getUriForFile(
                getContext(), getContext().getPackageName() + ".fileprovider", file
            );
            Intent intent = new Intent(Intent.ACTION_VIEW);
            intent.setDataAndType(uri, mimeType);
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
            if (intent.resolveActivity(getContext().getPackageManager()) != null) {
                getContext().startActivity(intent);
                call.resolve();
                return;
            }
            // Chrome e Samsung Internet conseguem exibir PDF, mas nem sempre
            // declaram o MIME application/pdf no filtro genérico do Android.
            // Tente explicitamente os navegadores instalados antes de salvar.
            String[] browsers = {"com.android.chrome", "com.sec.android.app.sbrowser"};
            for (String browser : browsers) {
                Intent browserIntent = new Intent(Intent.ACTION_VIEW);
                browserIntent.setDataAndType(uri, mimeType);
                browserIntent.setPackage(browser);
                browserIntent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_ACTIVITY_NEW_TASK);
                if (browserIntent.resolveActivity(getContext().getPackageManager()) != null) {
                    getContext().startActivity(browserIntent);
                    call.resolve();
                    return;
                }
            }
            saveToDownloads(bytes, safeName, mimeType);
            com.getcapacitor.JSObject result = new com.getcapacitor.JSObject();
            result.put("saved", true);
            result.put("fileName", safeName);
            call.resolve(result);
        } catch (Exception error) {
            call.reject("Não foi possível abrir o documento no celular", error);
        }
    }

    private void saveToDownloads(byte[] bytes, String fileName, String mimeType) throws Exception {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ContentValues values = new ContentValues();
            values.put(MediaStore.Downloads.DISPLAY_NAME, fileName);
            values.put(MediaStore.Downloads.MIME_TYPE, mimeType);
            values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/Parts ERP");
            values.put(MediaStore.Downloads.IS_PENDING, 1);
            Uri uri = getContext().getContentResolver().insert(
                MediaStore.Downloads.EXTERNAL_CONTENT_URI, values
            );
            if (uri == null) throw new IllegalStateException("Não foi possível criar o arquivo em Downloads");
            try (java.io.OutputStream output = getContext().getContentResolver().openOutputStream(uri)) {
                if (output == null) throw new IllegalStateException("Não foi possível gravar o arquivo");
                output.write(bytes);
            }
            values.clear();
            values.put(MediaStore.Downloads.IS_PENDING, 0);
            getContext().getContentResolver().update(uri, values, null, null);
            return;
        }
        File downloads = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
        if (!downloads.exists() && !downloads.mkdirs()) throw new IllegalStateException("Não foi possível acessar Downloads");
        try (FileOutputStream output = new FileOutputStream(new File(downloads, fileName))) {
            output.write(bytes);
        }
    }
}
