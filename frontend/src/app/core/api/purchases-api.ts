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
export class PurchasesApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  purchaseImportProfiles(): Observable<{
    schema: string;
    profiles: Array<{ profile_id: string; name: string; kind: string; version: number }>;
  }> {
    return this.http.get<{
      schema: string;
      profiles: Array<{ profile_id: string; name: string; kind: string; version: number }>;
    }>(`${this.base}/settings/purchase-import-profiles`);
  }
  uploadPurchaseImportProfile(
    file: File,
  ): Observable<{ profile_id: string; name: string; status: string }> {
    const form = new FormData();
    form.append('file', file, file.name);
    return this.http.post<{ profile_id: string; name: string; status: string }>(
      `${this.base}/settings/purchase-import-profiles`,
      form,
    );
  }
  deletePurchaseImportProfile(id: string): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(
      `${this.base}/settings/purchase-import-profiles/${encodeURIComponent(id)}`,
    );
  }
  analyzePurchaseDocument(file: File, profileId?: string): Observable<any> {
    const form = new FormData();
    form.append('file', file, file.name);
    const params = profileId ? { profile_id: profileId } : undefined;
    return this.http.post<any>(`${this.base}/purchases/import-document`, form, { params });
  }

  purchaseImportDuplicates(params: {
    document_access_key?: string;
    order_number?: string;
    origin?: string;
  }): Observable<{
    match: {
      purchase_id: string;
      purchase_number: string;
      purchase_status: string;
      cancelled: boolean;
    } | null;
  }> {
    return this.http.get<{
      match: {
        purchase_id: string;
        purchase_number: string;
        purchase_status: string;
        cancelled: boolean;
      } | null;
    }>(`${this.base}/purchases/import-document/duplicates`, { params: queryParams(params) });
  }

  confirmImportedPurchase(file: File, payload: unknown): Observable<Purchase> {
    const form = new FormData();
    form.append('file', file);
    form.append('payload', JSON.stringify(payload));
    return this.http.post<Purchase>(`${this.base}/purchases/import-document/confirm`, form);
  }
  purchases(params?: {
    limit?: number;
    offset?: number;
    search?: string;
    status?: string;
    startDate?: string;
    endDate?: string;
  }): Observable<PurchaseListOut> {
    return this.http.get<PurchaseListOut>(`${this.base}/purchases`, {
      params: queryParams({
        limit: params?.limit,
        offset: params?.offset,
        search: params?.search,
        status: params?.status,
        start_date: params?.startDate,
        end_date: params?.endDate,
      }),
    });
  }
  purchase(id: string): Observable<Purchase> {
    return this.http.get<Purchase>(`${this.base}/purchases/${id}`);
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

  cancelPurchaseWithReason(
    id: string,
    payload: { reason: string; resolution?: string; return_items?: unknown[] },
  ): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/cancel`, payload);
  }

  closePurchaseBalance(id: string, payload: { reason?: string | null }): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/close-balance`, payload);
  }

  deletePurchase(
    id: string,
    reason?: string,
  ): Observable<{ number: string; items_summary: string }> {
    const params = reason ? { reason } : undefined;
    return this.http.delete<{ number: string; items_summary: string }>(
      `${this.base}/purchases/${id}`,
      { params },
    );
  }

  updatePurchase(id: string, payload: unknown): Observable<Purchase> {
    return this.http.patch<Purchase>(`${this.base}/purchases/${id}`, payload);
  }

  addPurchaseItem(id: string, payload: unknown): Observable<Purchase> {
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/items`, payload);
  }

  removePurchaseItem(id: string, itemId: string): Observable<Purchase> {
    return this.http.delete<Purchase>(`${this.base}/purchases/${id}/items/${itemId}`);
  }

  suppliers(): Observable<
    Array<{
      id: string;
      name: string;
      contact: string | null;
      default_delivery_days: number | null;
      default_payment_terms: string | null;
    }>
  > {
    return this.http.get<
      Array<{
        id: string;
        name: string;
        contact: string | null;
        default_delivery_days: number | null;
        default_payment_terms: string | null;
      }>
    >(`${this.base}/suppliers`);
  }

  createSupplier(payload: unknown): Observable<{
    id: string;
    name: string;
    default_delivery_days: number | null;
    default_payment_terms: string | null;
  }> {
    return this.http.post<{
      id: string;
      name: string;
      default_delivery_days: number | null;
      default_payment_terms: string | null;
    }>(`${this.base}/suppliers`, payload);
  }

  receivePurchaseInFull(
    id: string,
    options?: { create_products?: boolean; observation?: string },
  ): Observable<Purchase> {
    const params: Record<string, string> = {};
    if (options?.create_products) params['create_products'] = 'true';
    if (options?.observation) params['observation'] = options.observation;
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/receive-all`, {}, { params });
  }

  settlePurchasePayable(
    purchaseId: string,
    payableId: string,
    payload: unknown = {},
  ): Observable<unknown> {
    return this.http.post(
      `${this.base}/purchases/${purchaseId}/payables/${payableId}/settle`,
      payload,
    );
  }

  updatePurchasePayable(
    purchaseId: string,
    payableId: string,
    payload: unknown,
  ): Observable<unknown> {
    return this.http.patch(`${this.base}/purchases/${purchaseId}/payables/${payableId}`, payload);
  }
  updatePurchaseItem(id: string, itemId: string, payload: unknown): Observable<Purchase> {
    return this.http.patch<Purchase>(`${this.base}/purchases/${id}/items/${itemId}`, payload);
  }
  uploadPurchaseAttachments(id: string, files: File[]): Observable<Purchase> {
    const form = new FormData();
    files.forEach((file) => form.append('files', file, file.name));
    return this.http.post<Purchase>(`${this.base}/purchases/${id}/attachments`, form);
  }
  downloadPurchaseAttachment(id: string, attachmentId: string, filename: string): void {
    this.http
      .get(`${this.base}/purchases/${id}/attachments/${attachmentId}`, { responseType: 'blob' })
      .subscribe((blob) => {
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.click();
        URL.revokeObjectURL(url);
      });
  }
}
