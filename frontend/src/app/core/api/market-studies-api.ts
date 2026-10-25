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
  MarketStudyList,
  MarketStudyConnector,
  VehicleMarketOverview,
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
  marketStudyDefaults(): Observable<{
    marketplace_fee_pct: string | null;
    target_margin_pct: string | null;
    profile_version: number | null;
    missing_company_fields: string[];
    legacy_marketplace_fee_pct: number;
  }> {
    return this.http.get<{
      marketplace_fee_pct: string | null;
      target_margin_pct: string | null;
      profile_version: number | null;
      missing_company_fields: string[];
      legacy_marketplace_fee_pct: number;
    }>(`${this.base}/market-studies/defaults`);
  }
  marketStudies(params?: {
    search?: string;
    status?: string;
    decision?: string;
    limit?: number;
    offset?: number;
  }): Observable<MarketStudyList> {
    return this.http.get<MarketStudyList>(`${this.base}/market-studies`, {
      params: queryParams(params ?? {}),
    });
  }
  marketStudy(id: string): Observable<MarketStudy> {
    return this.http.get<MarketStudy>(`${this.base}/market-studies/${id}`);
  }
  createMarketStudy(payload: {
    mode?: 'legacy' | 'brand' | 'nationality';
    brand?: string;
    nationality?: string;
    region?: string;
    vehicle_categories?: string[];
    include_suppliers_china?: boolean;
    include_competitor_links?: boolean;
    search_term?: string;
    sku?: string;
    category_id?: string;
    landed_cost?: number;
    target_margin_pct?: number;
    marketplace_fee_pct?: number;
    shipping_cost?: number | null;
    fixed_fee?: number | null;
    outbound_shipping?: number | null;
    oem?: string;
    application?: string;
    fitments?: {
      make: string;
      model: string;
      year_from?: number | null;
      year_to?: number | null;
      engine?: string | null;
      version?: string | null;
    }[];
  }): Observable<MarketStudy> {
    return this.http.post<MarketStudy>(`${this.base}/market-studies`, payload);
  }
  vehicleMarket(params: Record<string, string> = {}): Observable<VehicleMarketOverview> {
    return this.http.get<VehicleMarketOverview>(
      `${this.base}/market-studies/vehicle-market`,
      { params: queryParams(params) },
    );
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
