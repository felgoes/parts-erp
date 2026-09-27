import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
import { AuthToken } from './models';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
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
        tap((session) => {
          sessionStorage.setItem(this.storageKey, JSON.stringify(session));
          this.session.set(session);
        }),
      );
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
}
