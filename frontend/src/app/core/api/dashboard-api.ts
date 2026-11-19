import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { apiUrl } from '../api-url';
import { Observable } from 'rxjs';
import {
  Customer,
  DashboardSummary,
  DashboardSalesPage,
  DashboardFinancialMetrics,
  DashboardMarketplaceMetrics,
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
export class DashboardApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  dashboard(startDate: string, endDate: string, recentSalesOffset = 0, recentSalesPageSize = 10): Observable<DashboardSummary> {
    return this.http.get<DashboardSummary>(`${this.base}/dashboard/summary`, {
      params: { start_date: startDate, end_date: endDate, recent_sales_offset: recentSalesOffset, recent_sales_page_size: recentSalesPageSize },
    });
  }
  dashboardRecentSales(startDate: string, endDate: string, offset: number, pageSize = 10): Observable<DashboardSalesPage> {
    return this.http.get<DashboardSalesPage>(`${this.base}/dashboard/recent-sales`, {
      params: { start_date: startDate, end_date: endDate, offset, page_size: pageSize },
    });
  }
  dashboardMarketplace(startDate: string, endDate: string): Observable<DashboardMarketplaceMetrics> {
    return this.http.get<DashboardMarketplaceMetrics>(`${this.base}/dashboard/mercadolivre`, {
      params: { start_date: startDate, end_date: endDate },
    });
  }
  refreshDashboardMarketplace(startDate: string, endDate: string, force = false): Observable<{ accepted: boolean; status: string }> {
    return this.http.post<{ accepted: boolean; status: string }>(
      `${this.base}/dashboard/mercadolivre/refresh`, null,
      { params: { start_date: startDate, end_date: endDate, force } },
    );
  }
  dashboardFinancial(startDate: string, endDate: string): Observable<DashboardFinancialMetrics> {
    return this.http.get<DashboardFinancialMetrics>(`${this.base}/dashboard/financial`, {
      params: { start_date: startDate, end_date: endDate },
    });
  }
  financeOverview(startDate: string, endDate: string): Observable<FinanceOverview> {
    return this.http.get<FinanceOverview>(`${this.base}/finance/overview`, {
      params: { start_date: startDate, end_date: endDate },
    });
  }
}
