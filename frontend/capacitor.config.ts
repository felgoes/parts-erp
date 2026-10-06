import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'br.com.goesautoparts.erp',
  appName: 'Goes Auto Parts ERP',
  webDir: 'dist/frontend/browser',
  bundledWebRuntime: false,
  android: {
    // Keep WebView content clear of Android 15+ status and navigation bars.
    adjustMarginsForEdgeToEdge: 'auto',
  },
  // Keep the installed APK pointed at the ERP so web releases arrive without reinstalling.
  server: {
    url: 'https://erp.goesautoparts.com.br',
    cleartext: false,
    allowNavigation: ['erp.goesautoparts.com.br'],
  },
};

export default config;
