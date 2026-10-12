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
  telemetrySummary(startDate: string, endDate: string): Observable<TelemetrySummary> {
    return this.http.get<TelemetrySummary>(this.base + '/telemetry/summary', {
      params: { start_date: startDate, end_date: endDate },
    });
  }
}
