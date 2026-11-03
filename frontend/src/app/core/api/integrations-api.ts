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
  TelemetrySummary,
  AdPerformanceSummary,
  ErpSettings,
  PushPreference,
  PushSound,
  PushNotification,
} from '../models';
import { queryParams } from './http-helpers';
@Injectable({ providedIn: 'root' })
export class IntegrationsApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  adPerformance(params: { start_date: string; end_date: string; channel?: string; status?: string; search?: string; page?: number; page_size?: number; sort_by?: string; sort_direction?: string }): Observable<AdPerformanceSummary> {
    return this.http.get<AdPerformanceSummary>(this.base + '/telemetry/ad-performance', { params: queryParams(params) });
  }
  refreshAdPerformance(): Observable<{ accepted: boolean; status: string }> {
    return this.http.post<{ accepted: boolean; status: string }>(this.base + '/telemetry/ad-performance/refresh', {});
  }
  telemetrySummary(startDate: string, endDate: string): Observable<TelemetrySummary> {
    return this.http.get<TelemetrySummary>(this.base + '/telemetry/summary', {
      params: { start_date: startDate, end_date: endDate },
    });
  }
}
