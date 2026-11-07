import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { Capacitor, PluginListenerHandle, registerPlugin } from '@capacitor/core';
import { firstValueFrom } from 'rxjs';
import type { AuthService } from './auth.service';
import type { User } from './models';
import { notificationDestination } from './notification-destination';
import { apiUrl } from './api-url';

interface NativePushNotifications {
  register(): Promise<{ token: string }>;
  takeLaunch(): Promise<Record<string, unknown>>;
  addListener(event: 'notificationOpened', listener: (action: Record<string, unknown>) => void): Promise<PluginListenerHandle>;
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
  private readonly router = inject(Router);
  private launch: Record<string, unknown> | undefined;
  private launchInitialized = false;
  private resolvingLaunch = false;
  private registeredToken = '';
  private registrationRequest: Promise<void> | null = null;
  readonly registrationState = signal<PushRegistrationState>({
    status: 'idle',
    message: 'Aguardando verificação deste dispositivo.',
  });

  isAndroidApp(): boolean {
    return Capacitor.isNativePlatform() && Capacitor.getPlatform() === 'android';
  }

  async listenForNotificationOpens(auth: AuthService): Promise<void> {
    if (!this.isAndroidApp() || this.launchInitialized) return;
    this.launchInitialized = true;
    this.router.events.subscribe((event) => {
      if (event instanceof NavigationEnd) void this.routePendingNotification(auth);
    });
    try {
      await nativePush.addListener('notificationOpened', (action) => this.queueLaunch(action, auth));
      this.queueLaunch(await nativePush.takeLaunch(), auth);
    } catch {
      // An older Android release can still register and receive push.
    }
  }

  private queueLaunch(action: Record<string, unknown>, auth: AuthService): void {
    if (typeof action['parts_event_id'] !== 'string') return;
    this.launch = action;
    void this.routePendingNotification(auth);
  }

  private async routePendingNotification(auth: AuthService): Promise<void> {
    const launch = this.launch;
    if (!launch || this.resolvingLaunch || !this.router.navigated
      || this.router.url.startsWith('/login') || !auth.isAuthenticated()) return;

    this.resolvingLaunch = true;
    try {
      const user = await firstValueFrom(this.http.get<User>(apiUrl('/auth/me')));
      if (this.launch !== launch || !auth.isAuthenticated()) return;
      const target = notificationDestination(launch, user.role);
      this.launch = undefined;
      await this.router.navigate([target.route], { queryParams: target.query });
    } catch {
      // Keep the target if an expired session redirects to login.
    } finally {
      this.resolvingLaunch = false;
      if (this.launch && this.launch !== launch) void this.routePendingNotification(auth);
    }
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
        message:
          'O Firebase não conseguiu registrar este dispositivo. Confira o Google Play Services e tente novamente.',
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
