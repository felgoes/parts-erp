import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { apiUrl } from './api-url';
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
  CustomerDetail,
  User,
  TelemetrySummary,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  dashboard(startDate: string, endDate: string): Observable<DashboardSummary> {
    return this.http.get<DashboardSummary>(`${this.base}/dashboard/summary`, { params: { start_date: startDate, end_date: endDate } });
  }
  dashboardFinancial(startDate: string, endDate: string): Observable<DashboardFinancialMetrics> {
    return this.http.get<DashboardFinancialMetrics>(`${this.base}/dashboard/financial`, { params: { start_date: startDate, end_date: endDate } });
  }
  financeOverview(startDate: string, endDate: string): Observable<FinanceOverview> {
    return this.http.get<FinanceOverview>(`${this.base}/finance/overview`, {
      params: { start_date: startDate, end_date: endDate },
    });
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
  updateProduct(id: string, payload: Partial<Product>): Observable<Product> {
    return this.http.patch<Product>(`${this.base}/products/${id}`, payload);
  }
  uploadProductImages(id: string, files: File[]): Observable<Product> {
    const form = new FormData();
    files.forEach((file) => form.append('files', file, file.name));
    return this.http.post<Product>(`${this.base}/products/${id}/images`, form);
  }
  deleteProductImage(id: string, imageId: string): Observable<Product> {
    return this.http.delete<Product>(`${this.base}/products/${id}/images/${imageId}`);
  }
  productChannelMetadata(provider: 'mercadolivre' | 'shopee', query = '', categoryId = ''): Observable<ProductChannelMetadata> {
    let params = new HttpParams();
    if (query) params = params.set('query', query);
    if (categoryId) params = params.set('category_id', categoryId);
    return this.http.get<ProductChannelMetadata>(`${this.base}/products/channel-metadata/${provider}`, { params });
  }
  saveProductChannelDraft(id: string, provider: 'mercadolivre' | 'shopee', draft: ProductChannelDraft): Observable<ProductDetail> {
    return this.http.put<ProductDetail>(`${this.base}/products/${id}/channels/${provider}/draft`, draft);
  }
  publishProductChannel(id: string, provider: 'mercadolivre' | 'shopee'): Observable<ProductDetail> {
    return this.http.post<ProductDetail>(`${this.base}/products/${id}/channels/${provider}/publish`, {});
  }
  adjustStock(id: string, quantity: number, reason: string): Observable<Product> {
    return this.http.post<Product>(`${this.base}/products/${id}/adjust-stock`, {
      quantity,
      reason,
    });
  }
  purchases(): Observable<Purchase[]> {
    return this.http.get<Purchase[]>(`${this.base}/purchases`);
  }
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
  createPurchaseFromMarketStudy(studyId: string, sku: string, quantity: number): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/market-studies/${studyId}/purchase`, { sku, quantity });
  }
  createPurchase(payload: unknown): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/purchases`, payload);
  }
  addPurchaseQuote(id: string, payload: unknown): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/quotes`, payload);
  }
  selectPurchaseQuote(id: string, quoteId: string): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/select-quote/${quoteId}`, {});
  }
  placePurchaseOrder(id: string): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/place-order`, {});
  }
  receivePurchase(id: string, payload: unknown): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/receive`, payload);
  }
  cancelPurchase(id: string): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/cancel`, {});
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
  updateUser(id: string, payload: { email?: string; full_name?: string; password?: string; role?: User['role']; active?: boolean }): Observable<User> {
    return this.http.patch<User>(`${this.base}/users/${id}`, payload);
  }
  automateMarketplaceOrder(id: string): Observable<MarketplaceOrder> {
    return this.http.post<MarketplaceOrder>(`${this.base}/integrations/mercadolivre/orders/${id}/automate`, {});
  }
  invoices(startDate: string, endDate: string): Observable<Invoice[]> {
    return this.http.get<Invoice[]>(`${this.base}/invoices`, { params: { start_date: startDate, end_date: endDate } });
  }
  invoice(id: string): Observable<Invoice> {
    return this.http.get<Invoice>(`${this.base}/invoices/${id}`);
  }
  receiveAfterSale(caseId: string, items: { item_id: string; received_quantity: number }[], notes?: string): Observable<AfterSaleCase> {
    return this.http.post<AfterSaleCase>(`${this.base}/after-sales/${caseId}/receive`, { items, notes });
  }
  inspectAfterSale(
    caseId: string,
    items: { item_id: string; restock_quantity: number; disposition: 'restock' | 'mixed' | 'damaged' | 'discarded'; notes?: string }[],
  ): Observable<AfterSaleCase> {
    return this.http.post<AfterSaleCase>(`${this.base}/after-sales/${caseId}/inspect`, { items });
  }
  closeAfterSaleWithoutStock(caseId: string, note: string): Observable<AfterSaleCase> {
    return this.http.post<AfterSaleCase>(`${this.base}/after-sales/${caseId}/close-without-stock`, { note });
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
