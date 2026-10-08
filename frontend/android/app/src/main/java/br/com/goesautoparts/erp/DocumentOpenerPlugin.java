package br.com.goesautoparts.erp;

import android.content.Intent;
import android.net.Uri;
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
            if (intent.resolveActivity(getContext().getPackageManager()) == null) {
                call.reject("Nenhum aplicativo consegue abrir este documento");
                return;
            }
            getContext().startActivity(intent);
            call.resolve();
        } catch (Exception error) {
            call.reject("Não foi possível abrir o documento no celular", error);
        }
    }
}
