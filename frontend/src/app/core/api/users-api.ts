import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { apiUrl } from '../api-url';
import { Observable } from 'rxjs';
import {
  Customer,
  DashboardSummary,
  DashboardFinancialMetrics,
  FinanceOverview,
  Invoice,
  MarketplaceOrder,
  MarketplaceOrderEvent,
  MarketStudy,
  MarketStudyConnector,
  MarketplaceStatus,
  AfterSaleCase,
  MarketplaceConfig,
  ShopeeConfig,
  ShopeeStatus,
  Product,
  ProductDetail,
  ProductChannelMetadata,
  ProductChannelDraft,
  Purchase,
  PurchaseListItem,
  PurchaseListOut,
  PayableDetail,
  PayableListResponse,
  PayableReport,
  CustomerDetail,
  User,
  LoginAttempts,
  TelemetrySummary,
  ErpSettings,
  PushPreference,
  PushSound,
  PushNotification,
} from '../models';
import { queryParams } from './http-helpers';
@Injectable({ providedIn: 'root' })
export class UsersApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  users(): Observable<User[]> {
    return this.http.get<User[]>(`${this.base}/users`);
  }
  createUser(payload: {
    email: string;
    full_name: string;
    password: string;
    role: User['role'];
  }): Observable<User> {
    return this.http.post<User>(`${this.base}/users`, payload);
  }
  resetUserPassword(id: string, password: string): Observable<User> {
    return this.http.patch<User>(`${this.base}/users/${id}/password`, { password });
  }
  updateUser(
    id: string,
    payload: {
      email?: string;
      full_name?: string;
      password?: string;
      role?: User['role'];
      active?: boolean;
    },
  ): Observable<User> {
    return this.http.patch<User>(`${this.base}/users/${id}`, payload);
  }
  updateMyProfile(email: string): Observable<User> {
    return this.http.patch<User>(`${this.base}/users/me/profile`, { email });
  }
  updateMyPreferences(financialSummaryHidden: boolean): Observable<User> {
    return this.http.patch<User>(`${this.base}/users/me/preferences`, {
      financial_summary_hidden: financialSummaryHidden,
    });
  }
  uploadMyAvatar(file: File): Observable<User> {
    const body = new FormData();
    body.append('image', file);
    return this.http.post<User>(`${this.base}/users/me/avatar`, body);
  }
  myAvatar(): Observable<Blob> {
    return this.http.get(`${this.base}/users/me/avatar`, { responseType: 'blob' });
  }
  loginAttempts(): Observable<LoginAttempts> {
    return this.http.get<LoginAttempts>(`${this.base}/auth/attempts`);
  }
  releaseLoginAttempts(payload: { email?: string; ip?: string }): Observable<LoginAttempts> {
    return this.http.post<LoginAttempts>(`${this.base}/auth/attempts/reset`, payload);
  }
}
