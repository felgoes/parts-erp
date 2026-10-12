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
export class CustomersApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  customers(): Observable<Customer[]> {
    return this.http.get<Customer[]>(`${this.base}/customers`);
  }
  customerDetail(id: string): Observable<CustomerDetail> {
    return this.http.get<CustomerDetail>(`${this.base}/customers/${id}`);
  }
  createCustomer(payload: Partial<Customer>): Observable<Customer> {
    return this.http.post<Customer>(`${this.base}/customers`, payload);
  }
}
