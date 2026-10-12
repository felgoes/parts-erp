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
export class MarketplaceApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  automateMarketplaceOrder(id: string): Observable<MarketplaceOrder> {
    return this.http.post<MarketplaceOrder>(
      `${this.base}/integrations/mercadolivre/orders/${id}/automate`,
      {},
    );
  }
  requestMarketplaceInvoice(id: string): Observable<MarketplaceOrder> {
    return this.http.post<MarketplaceOrder>(
      `${this.base}/integrations/mercadolivre/orders/${id}/fiscal`,
      {},
    );
  }
  retryMarketplaceLabel(id: string): Observable<MarketplaceOrder> {
    return this.http.post<MarketplaceOrder>(
      `${this.base}/integrations/mercadolivre/orders/${id}/label`,
      {},
    );
  }
  marketplaceStatus(): Observable<MarketplaceStatus> {
    return this.http.get<MarketplaceStatus>(`${this.base}/integrations/mercadolivre/status`);
  }
  marketplaceConfig(): Observable<MarketplaceConfig> {
    return this.http.get<MarketplaceConfig>(`${this.base}/integrations/mercadolivre/config`);
  }
  saveMarketplaceConfig(payload: Record<string, unknown>): Observable<MarketplaceConfig> {
    return this.http.put<MarketplaceConfig>(
      `${this.base}/integrations/mercadolivre/config`,
      payload,
    );
  }
  marketplaceOrders(): Observable<MarketplaceOrder[]> {
    return this.http.get<MarketplaceOrder[]>(`${this.base}/integrations/mercadolivre/orders`);
  }
  marketplaceOrder(id: string): Observable<MarketplaceOrder> {
    return this.http.get<MarketplaceOrder>(`${this.base}/integrations/mercadolivre/orders/${id}`);
  }
  marketplaceOrderHistory(id: string): Observable<MarketplaceOrderEvent[]> {
    return this.http.get<MarketplaceOrderEvent[]>(
      `${this.base}/integrations/mercadolivre/orders/${id}/history`,
    );
  }
  syncMarketplace(): Observable<{ accepted: boolean; message: string }> {
    return this.http.post<{ accepted: boolean; message: string }>(
      `${this.base}/integrations/mercadolivre/sync`,
      {},
    );
  }
  connectMarketplace(): Observable<{ authorization_url: string }> {
    return this.http.get<{ authorization_url: string }>(
      `${this.base}/integrations/mercadolivre/connect`,
    );
  }

  shopeeStatus(): Observable<ShopeeStatus> {
    return this.http.get<ShopeeStatus>(this.base + '/integrations/shopee/status');
  }
  shopeeConfig(): Observable<ShopeeConfig> {
    return this.http.get<ShopeeConfig>(this.base + '/integrations/shopee/config');
  }
  saveShopeeConfig(payload: Record<string, unknown>): Observable<ShopeeConfig> {
    return this.http.put<ShopeeConfig>(this.base + '/integrations/shopee/config', payload);
  }
  connectShopee(): Observable<{ authorization_url: string }> {
    return this.http.get<{ authorization_url: string }>(this.base + '/integrations/shopee/connect');
  }
}
