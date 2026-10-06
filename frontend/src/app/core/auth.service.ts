import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, firstValueFrom, tap } from 'rxjs';
import { BiometricStatus, biometricLogin } from './biometric-login';
import { AuthToken, User } from './models';
import { PushNotificationsService } from './push-notifications.service';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly pushNotifications = inject(PushNotificationsService);
  private readonly storageKey = 'parts-erp-session';
  private readonly session = signal<AuthToken | null>(this.restore());
  readonly user = computed(() => this.session()?.user ?? null);
  readonly isAuthenticated = computed(() => !!this.session()?.access_token);
  get token(): string | null {
    return this.session()?.access_token ?? null;
  }
  login(email: string, password: string): Observable<AuthToken> {
    const body = new HttpParams().set('username', email).set('password', password);
    return this.http
      .post<AuthToken>('/api/v1/auth/login', body.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      })
      .pipe(
        tap((session) => this.storeSession(session)),
      );
  }
  async biometricStatus(): Promise<BiometricStatus> {
    if (!biometricLogin.isNativeAndroid()) {
      return { available: false, configured: false, email: null };
    }
    try {
      return await biometricLogin.status();
    } catch {
      return { available: false, configured: false, email: null };
    }
  }
  async enableBiometric(email: string): Promise<void> {
    const enrollment = await firstValueFrom(
      this.http.post<{ credential: string }>('/api/v1/auth/biometric/credentials', {
        device_name: 'Parts ERP no Android',
      }),
    );
    await biometricLogin.saveCredential(enrollment.credential, email);
  }
  async loginWithBiometric(): Promise<AuthToken> {
    const nativeCredential = await biometricLogin.authenticate();
    try {
      const session = await firstValueFrom(
        this.http.post<AuthToken>('/api/v1/auth/biometric/login', {
          credential: nativeCredential.credential,
        }),
      );
      this.storeSession(session);
      return session;
    } catch (error) {
      await biometricLogin.clearCredential();
      throw error;
    }
  }
  updateCurrentUser(user: User): void {
    const current = this.session();
    if (!current) return;
    const updated = { ...current, user };
    sessionStorage.setItem(this.storageKey, JSON.stringify(updated));
    this.session.set(updated);
  }
  logout(): void {
    sessionStorage.removeItem(this.storageKey);
    this.session.set(null);
    this.router.navigateByUrl('/login');
  }
  private restore(): AuthToken | null {
    try {
      return JSON.parse(sessionStorage.getItem(this.storageKey) ?? 'null');
    } catch {
      sessionStorage.removeItem(this.storageKey);
      return null;
    }
  }
  private storeSession(session: AuthToken): void {
    sessionStorage.setItem(this.storageKey, JSON.stringify(session));
    this.session.set(session);
    void this.pushNotifications.enableForCurrentDevice();
  }
}
