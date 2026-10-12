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
export class PayablesApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  payables(
    params: Record<string, string | number | boolean> = {},
  ): Observable<PayableListResponse> {
    return this.http.get<PayableListResponse>(`${this.base}/payables`, {
      params: queryParams(params),
    });
  }

  payable(id: string): Observable<PayableDetail> {
    return this.http.get<PayableDetail>(`${this.base}/payables/${id}`);
  }

  payableReport(params: Record<string, string | number | boolean> = {}): Observable<PayableReport> {
    return this.http.get<PayableReport>(`${this.base}/payables/report`, {
      params: queryParams(params),
    });
  }

  addPayablePayment(id: string, payload: unknown): Observable<PayableDetail> {
    return this.http.post<PayableDetail>(`${this.base}/payables/${id}/payments`, payload);
  }

  removePayablePayment(id: string, paymentId: string): Observable<PayableDetail> {
    return this.http.delete<PayableDetail>(`${this.base}/payables/${id}/payments/${paymentId}`);
  }

  reconcilePayablePayment(
    id: string,
    paymentId: string,
    reconciled: boolean,
  ): Observable<PayableDetail> {
    return this.http.post<PayableDetail>(
      `${this.base}/payables/${id}/payments/${paymentId}/reconcile`,
      { reconciled },
    );
  }

  updatePayable(id: string, payload: unknown): Observable<PayableDetail> {
    return this.http.patch<PayableDetail>(`${this.base}/payables/${id}`, payload);
  }

  downloadPayablesCsv(params: Record<string, string | number | boolean> = {}): void {
    this.http
      .get(`${this.base}/payables/export.csv`, {
        params: queryParams(params),
        responseType: 'blob',
      })
      .subscribe((blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = 'contas-a-pagar.csv';
        link.click();
        URL.revokeObjectURL(url);
      });
  }
}
