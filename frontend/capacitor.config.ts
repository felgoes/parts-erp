import type { CapacitorConfig } from '@capacitor/cli';

const config: CapacitorConfig = {
  appId: 'br.com.goesautoparts.erp',
  appName: 'Goes Auto Parts ERP',
  webDir: 'dist/frontend/browser',
  bundledWebRuntime: false,
  // Carrega o ERP publicado para receber atualizações do front sem reinstalar o APK.
  server: {
    url: 'https://erp.goesautoparts.com.br',
    cleartext: false,
    allowNavigation: ['erp.goesautoparts.com.br'],
  },
};

export default config;
