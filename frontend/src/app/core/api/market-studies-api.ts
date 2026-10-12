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
export class MarketStudiesApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  marketStudies(): Observable<MarketStudy[]> {
    return this.http.get<MarketStudy[]>(`${this.base}/market-studies`);
  }
  createMarketStudy(payload: {
    search_term: string;
    sku?: string;
    category_id?: string;
    landed_cost: number;
    target_margin_pct: number;
    marketplace_fee_pct: number;
    shipping_cost: number;
  }): Observable<MarketStudy> {
    return this.http.post<MarketStudy>(`${this.base}/market-studies`, payload);
  }
  marketStudyConnector(): Observable<MarketStudyConnector> {
    return this.http.get<MarketStudyConnector>(`${this.base}/market-studies/connector`);
  }
  saveMarketStudyConnector(payload: {
    provider: MarketStudyConnector['provider'];
    model: string;
    base_url?: string;
    api_key?: string;
    enabled: boolean;
  }): Observable<MarketStudyConnector> {
    return this.http.put<MarketStudyConnector>(`${this.base}/market-studies/connector`, payload);
  }
  createPurchaseFromMarketStudy(
    studyId: string,
    sku: string,
    quantity: number,
  ): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/market-studies/${studyId}/purchase`, {
      sku,
      quantity,
    });
  }
}
