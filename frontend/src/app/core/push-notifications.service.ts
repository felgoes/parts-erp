import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { firstValueFrom } from 'rxjs';
import { apiUrl } from './api-url';

interface NativePushNotifications {
  register(): Promise<{ token: string }>;
}

export type PushRegistrationStatus = 'idle' | 'checking' | 'registered' | 'unavailable' | 'error';

export interface PushRegistrationState {
  status: PushRegistrationStatus;
  message: string;
}

const nativePush = registerPlugin<NativePushNotifications>('PushNotifications');

@Injectable({ providedIn: 'root' })
export class PushNotificationsService {
  private readonly http = inject(HttpClient);
  private registeredToken = '';
  private registrationRequest: Promise<void> | null = null;
  readonly registrationState = signal<PushRegistrationState>({
    status: 'idle',
    message: 'Aguardando verificação deste dispositivo.',
  });

  isAndroidApp(): boolean {
    return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android';
  }

  async enableForCurrentDevice(): Promise<void> {
    if (!this.isAndroidApp()) {
      this.registrationState.set({
        status: 'unavailable',
        message: 'Abra esta tela no aplicativo Android para verificar o registro do push.',
      });
      return;
    }
    if (this.registeredToken) {
      this.setRegistered();
      return;
    }
    if (this.registrationRequest) return this.registrationRequest;
    this.registrationState.set({
      status: 'checking',
      message: 'Verificando o Firebase e registrando este dispositivo…',
    });
    this.registrationRequest = this.registerDevice();
    try {
      await this.registrationRequest;
    } catch {
      this.registrationState.set({
        status: 'error',
        message: 'O Firebase não conseguiu registrar este dispositivo. Confira o Google Play Services e tente novamente.',
      });
    } finally {
      this.registrationRequest = null;
    }
  }

  private async registerDevice(): Promise<void> {
    const { token } = await nativePush.register();
    if (!token) throw new Error('Firebase não retornou um token para este dispositivo.');
    if (token !== this.registeredToken) {
      await firstValueFrom(
        this.http.post<void>(apiUrl('/push/devices'), {
          token,
          platform: 'android',
          sound_settings_version: 2,
        }),
      );
      this.registeredToken = token;
    }
    this.setRegistered();
  }

  private setRegistered(): void {
    this.registrationState.set({
      status: 'registered',
      message: 'Este dispositivo está registrado no servidor para receber notificações.',
    });
  }
}
