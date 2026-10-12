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
export class ProductsApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  products(
    search = '',
    lowStock = false,
    stockType?: 'product' | 'warehouse',
  ): Observable<Product[]> {
    let params = new HttpParams();
    if (search) params = params.set('search', search);
    if (lowStock) params = params.set('low_stock', true);
    if (stockType) params = params.set('stock_type', stockType);
    return this.http.get<Product[]>(`${this.base}/products`, { params });
  }
  productMovements(id: string): Observable<import('../models').StockMovement[]> {
    return this.http.get<import('../models').StockMovement[]>(
      `${this.base}/products/${id}/movements`,
    );
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
  productChannelMetadata(
    provider: 'mercadolivre' | 'shopee',
    query = '',
    categoryId = '',
  ): Observable<ProductChannelMetadata> {
    let params = new HttpParams();
    if (query) params = params.set('query', query);
    if (categoryId) params = params.set('category_id', categoryId);
    return this.http.get<ProductChannelMetadata>(
      `${this.base}/products/channel-metadata/${provider}`,
      { params },
    );
  }
  saveProductChannelDraft(
    id: string,
    provider: 'mercadolivre' | 'shopee',
    draft: ProductChannelDraft,
  ): Observable<ProductDetail> {
    return this.http.put<ProductDetail>(
      `${this.base}/products/${id}/channels/${provider}/draft`,
      draft,
    );
  }
  publishProductChannel(
    id: string,
    provider: 'mercadolivre' | 'shopee',
  ): Observable<ProductDetail> {
    return this.http.post<ProductDetail>(
      `${this.base}/products/${id}/channels/${provider}/publish`,
      {},
    );
  }
  adjustStock(id: string, quantity: number, reason: string): Observable<Product> {
    return this.http.post<Product>(`${this.base}/products/${id}/adjust-stock`, {
      quantity,
      reason,
    });
  }
}
