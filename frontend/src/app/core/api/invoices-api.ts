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
export class InvoicesApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  invoices(startDate: string, endDate: string): Observable<Invoice[]> {
    return this.http.get<Invoice[]>(`${this.base}/invoices`, {
      params: { start_date: startDate, end_date: endDate },
    });
  }
  invoice(id: string): Observable<Invoice> {
    return this.http.get<Invoice>(`${this.base}/invoices/${id}`);
  }
  receiveAfterSale(
    caseId: string,
    items: { item_id: string; received_quantity: number }[],
    notes?: string,
  ): Observable<AfterSaleCase> {
    return this.http.post<AfterSaleCase>(`${this.base}/after-sales/${caseId}/receive`, {
      items,
      notes,
    });
  }
  inspectAfterSale(
    caseId: string,
    items: {
      item_id: string;
      restock_quantity: number;
      disposition: 'restock' | 'mixed' | 'damaged' | 'discarded';
      notes?: string;
    }[],
  ): Observable<AfterSaleCase> {
    return this.http.post<AfterSaleCase>(`${this.base}/after-sales/${caseId}/inspect`, { items });
  }
  closeAfterSaleWithoutStock(caseId: string, note: string): Observable<AfterSaleCase> {
    return this.http.post<AfterSaleCase>(`${this.base}/after-sales/${caseId}/close-without-stock`, {
      note,
    });
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
  invoiceDocumentBrowserUrl(invoiceId: string, documentId: string): Observable<{ url: string }> {
    return this.http.get<{ url: string }>(`${this.base}/invoices/documents/browser-url`, {
      params: { invoice_id: invoiceId, document_id: documentId },
    });
  }
}
