import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import {
  Customer,
  DashboardSummary,
  Invoice,
  MarketplaceOrder,
  MarketplaceStatus,
  MarketplaceConfig,
  Product,
  User,
} from './models';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1';
  dashboard(): Observable<DashboardSummary> {
    return this.http.get<DashboardSummary>(`${this.base}/dashboard/summary`);
  }
  products(search = '', lowStock = false): Observable<Product[]> {
    let params = new HttpParams();
    if (search) params = params.set('search', search);
    if (lowStock) params = params.set('low_stock', true);
    return this.http.get<Product[]>(`${this.base}/products`, { params });
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
  createCustomer(payload: Partial<Customer>): Observable<Customer> {
    return this.http.post<Customer>(`${this.base}/customers`, payload);
  }
  users(): Observable<User[]> {
    return this.http.get<User[]>(`${this.base}/users`);
  }
  createUser(payload: { email: string; full_name: string; password: string; role: User['role'] }): Observable<User> {
    return this.http.post<User>(`${this.base}/users`, payload);
  }
  invoices(): Observable<Invoice[]> {
    return this.http.get<Invoice[]>(`${this.base}/invoices`);
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
  connectMarketplace(): Observable<{ authorization_url: string }> {
    return this.http.get<{ authorization_url: string }>(
      `${this.base}/integrations/mercadolivre/connect`,
    );
  }
}
