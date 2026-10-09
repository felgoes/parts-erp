import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { firstValueFrom } from 'rxjs';
import { apiUrl } from './api-url';

interface NativePushNotifications {
  register(): Promise<{ token: string }>;
}

const nativePush = registerPlugin<NativePushNotifications>('PushNotifications');

@Injectable({ providedIn: 'root' })
export class PushNotificationsService {
  private readonly http = inject(HttpClient);
  private registeredToken = '';
  private registrationRequest: Promise<void> | null = null;

  async enableForCurrentDevice(): Promise<void> {
    if (!Capacitor.isNativePlatform() || Capacitor.getPlatform() !== 'android') return;
    if (this.registeredToken) return;
    if (this.registrationRequest) return this.registrationRequest;
    this.registrationRequest = this.registerDevice();
    try {
      await this.registrationRequest;
    } catch {
      // Never interfere with login if Firebase is not configured in this APK yet.
    } finally {
      this.registrationRequest = null;
    }
  }

  private async registerDevice(): Promise<void> {
    const { token } = await nativePush.register();
    if (!token || token === this.registeredToken) return;
    await firstValueFrom(
      this.http.post<void>(apiUrl('/push/devices'), {
        token,
        platform: 'android',
        sound_settings_version: 2,
      }),
    );
    this.registeredToken = token;
  }
}
