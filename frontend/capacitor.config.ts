import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'br.com.goesautoparts.erp',
  appName: 'Parts ERP',
  webDir: 'dist/frontend/browser',
  bundledWebRuntime: false,
  android: {
    // MainActivity applies system bar and keyboard insets in one place.
    adjustMarginsForEdgeToEdge: 'disable',
  },
  // Keep the installed APK pointed at the ERP so web releases arrive without reinstalling.
  server: {
    url: 'https://erp.goesautoparts.com.br',
    cleartext: false,
    allowNavigation: ['erp.goesautoparts.com.br'],
  },
};

export default config;
