package br.com.goesautoparts.erp;

import android.os.Bundle;
import com.getcapacitor.BridgeActivity;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        registerPlugin(BiometricLoginPlugin.class);
        super.onCreate(savedInstanceState);
    }
}
