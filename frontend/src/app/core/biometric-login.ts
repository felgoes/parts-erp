import { Capacitor, registerPlugin } from '@capacitor/core';

export interface BiometricStatus {
  available: boolean;
  configured: boolean;
  email: string | null;
}

interface BiometricLoginPlugin {
  status(): Promise<BiometricStatus>;
  saveCredential(options: { credential: string; email: string }): Promise<void>;
  authenticate(): Promise<{ credential: string; email: string | null }>;
  clearCredential(): Promise<void>;
}

const nativeBiometric = registerPlugin<BiometricLoginPlugin>('BiometricLogin');

export const biometricLogin = {
  isNativeAndroid: () => Capacitor.getPlatform() === 'android',
  status: () => nativeBiometric.status(),
  saveCredential: (credential: string, email: string) =>
    nativeBiometric.saveCredential({ credential, email }),
  authenticate: () => nativeBiometric.authenticate(),
  clearCredential: () => nativeBiometric.clearCredential(),
};
