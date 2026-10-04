import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  Customer,
  DashboardSummary,
  DashboardFinancialMetrics,
  Invoice,
  MarketplaceOrder,
  MarketplaceOrderEvent,
  MarketplaceStatus,
  MarketplaceConfig,
  ShopeeConfig,
  ShopeeStatus,
  Product,
  ProductDetail,
  CustomerDetail,
  User,
  TelemetrySummary,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = this.apiBase();

  private apiBase(): string {
    return typeof window !== 'undefined' && window.location.protocol === 'capacitor:'
      ? 'https://erp.goesautoparts.com.br/api/v1'
      : '/api/v1';
  }
  dashboard(): Observable<DashboardSummary> {
    return this.http.get<DashboardSummary>(`${this.base}/dashboard/summary`);
  }
  dashboardFinancial(): Observable<DashboardFinancialMetrics> {
    return this.http.get<DashboardFinancialMetrics>(`${this.base}/dashboard/financial`);
  }
  products(search = '', lowStock = false): Observable<Product[]> {
    let params = new HttpParams();
    if (search) params = params.set('search', search);
    if (lowStock) params = params.set('low_stock', true);
    return this.http.get<Product[]>(`${this.base}/products`, { params });
  }
  productMovements(id: string): Observable<import('./models').StockMovement[]> {
    return this.http.get<import('./models').StockMovement[]>(`${this.base}/products/${id}/movements`);
  }
  productDetail(id: string): Observable<ProductDetail> {
    return this.http.get<ProductDetail>(`${this.base}/products/${id}/detail`);
  }
  syncMarketplaceStock(id: string): Observable<Product> {
    return this.http.post<Product>(`${this.base}/products/${id}/sync-marketplace`, {});
  }
  createProduct(payload: Partial<Product>): Observable<Product> {
    return this.http.post<Product>(`${this.base}/products`, payload);
  }
  adjustStock(id: string, quantity: number, reason: string): Observable<Product> {
    return this.http.post<Product>(`${this.base}/products/${id}/adjust-stock`, {
      quantity,
      reason,
    });
  }
  customers(): Observable<Customer[]> {
    return this.http.get<Customer[]>(`${this.base}/customers`);
  }
  customerDetail(id: string): Observable<CustomerDetail> {
    return this.http.get<CustomerDetail>(`${this.base}/customers/${id}`);
  }
  createCustomer(payload: Partial<Customer>): Observable<Customer> {
    return this.http.post<Customer>(`${this.base}/customers`, payload);
  }
  users(): Observable<User[]> {
    return this.http.get<User[]>(`${this.base}/users`);
  }
  createUser(payload: { email: string; full_name: string; password: string; role: User['role'] }): Observable<User> {
    return this.http.post<User>(`${this.base}/users`, payload);
  }
  resetUserPassword(id: string, password: string): Observable<User> {
    return this.http.patch<User>(`${this.base}/users/${id}/password`, { password });
  }
  updateUser(id: string, payload: { email?: string; full_name?: string; password?: string }): Observable<User> {
    return this.http.patch<User>(`${this.base}/users/${id}`, payload);
  }
  automateMarketplaceOrder(id: string): Observable<MarketplaceOrder> {
    return this.http.post<MarketplaceOrder>(`${this.base}/integrations/mercadolivre/orders/${id}/automate`, {});
  }
  invoices(): Observable<Invoice[]> {
    return this.http.get<Invoice[]>(`${this.base}/invoices`);
  }
  invoice(id: string): Observable<Invoice> {
    return this.http.get<Invoice>(`${this.base}/invoices/${id}`);
  }
  createInvoice(payload: unknown): Observable<Invoice> {
    return this.http.post<Invoice>(`${this.base}/invoices`, payload);
  }
  confirmInvoice(id: string): Observable<Invoice> {
    return this.http.post<Invoice>(`${this.base}/invoices/${id}/confirm`, {});
  }
  cancelInvoice(id: string): Observable<Invoice> {
    return this.http.post<Invoice>(`${this.base}/invoices/${id}/cancel`, {});
  }
  downloadInvoiceDocument(invoiceId: string, documentId: string): Observable<Blob> {
    return this.http.get(`${this.base}/invoices/${invoiceId}/documents/${documentId}`, {
      responseType: 'blob',
    });
  }
  marketplaceStatus(): Observable<MarketplaceStatus> {
    return this.http.get<MarketplaceStatus>(`${this.base}/integrations/mercadolivre/status`);
  }
  marketplaceConfig(): Observable<MarketplaceConfig> {
    return this.http.get<MarketplaceConfig>(`${this.base}/integrations/mercadolivre/config`);
  }
  saveMarketplaceConfig(payload: Record<string, unknown>): Observable<MarketplaceConfig> {
    return this.http.put<MarketplaceConfig>(`${this.base}/integrations/mercadolivre/config`, payload);
  }
  marketplaceOrders(): Observable<MarketplaceOrder[]> {
    return this.http.get<MarketplaceOrder[]>(`${this.base}/integrations/mercadolivre/orders`);
  }
  marketplaceOrder(id: string): Observable<MarketplaceOrder> {
    return this.http.get<MarketplaceOrder>(`${this.base}/integrations/mercadolivre/orders/${id}`);
  }
  marketplaceOrderHistory(id: string): Observable<MarketplaceOrderEvent[]> {
    return this.http.get<MarketplaceOrderEvent[]>(`${this.base}/integrations/mercadolivre/orders/${id}/history`);
  }
  syncMarketplace(): Observable<{ accepted: boolean; message: string }> {
    return this.http.post<{ accepted: boolean; message: string }>(
      `${this.base}/integrations/mercadolivre/sync`, {},
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
  telemetrySummary(startDate: string, endDate: string): Observable<TelemetrySummary> {
    return this.http.get<TelemetrySummary>(this.base + '/telemetry/summary', {
      params: { start_date: startDate, end_date: endDate },
    });
  }
}
