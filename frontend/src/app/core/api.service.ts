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
} from './models';
import { SettingsApi } from './api/settings-api';
import { PurchasesApi } from './api/purchases-api';
import { DashboardApi } from './api/dashboard-api';
import { ProductsApi } from './api/products-api';
import { PayablesApi } from './api/payables-api';
import { CustomersApi } from './api/customers-api';
import { UsersApi } from './api/users-api';
import { MarketplaceApi } from './api/marketplace-api';
import { InvoicesApi } from './api/invoices-api';
import { IntegrationsApi } from './api/integrations-api';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly settingsApi = inject(SettingsApi);
  private readonly purchasesApi = inject(PurchasesApi);
  private readonly dashboardApi = inject(DashboardApi);
  private readonly productsApi = inject(ProductsApi);
  private readonly payablesApi = inject(PayablesApi);
  private readonly customersApi = inject(CustomersApi);
  private readonly usersApi = inject(UsersApi);
  private readonly marketplaceApi = inject(MarketplaceApi);
  private readonly invoicesApi = inject(InvoicesApi);
  private readonly integrationsApi = inject(IntegrationsApi);
  erpSettings(): Observable<ErpSettings> {
    return this.settingsApi.erpSettings();
  }
  purchaseImportProfiles(): Observable<{
    schema: string;
    profiles: Array<{ profile_id: string; name: string; kind: string; version: number }>;
  }> {
    return this.purchasesApi.purchaseImportProfiles();
  }
  uploadPurchaseImportProfile(
    file: File,
  ): Observable<{ profile_id: string; name: string; status: string }> {
    return this.purchasesApi.uploadPurchaseImportProfile(file);
  }
  deletePurchaseImportProfile(id: string): Observable<{ status: string }> {
    return this.purchasesApi.deletePurchaseImportProfile(id);
  }
  analyzePurchaseDocument(file: File, profileId?: string): Observable<any> {
    return this.purchasesApi.analyzePurchaseDocument(file, profileId);
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
    return this.purchasesApi.purchaseImportDuplicates(params);
  }
  confirmImportedPurchase(file: File, payload: unknown): Observable<Purchase> {
    return this.purchasesApi.confirmImportedPurchase(file, payload);
  }
  saveErpSettings(
    settings: Pick<
      ErpSettings,
      | 'company_name'
      | 'company_short_name'
      | 'logo_data_url'
      | 'backup_enabled'
      | 'backup_frequency'
      | 'backup_time'
      | 'backup_retention_days'
      | 'backup_destination'
    > & {
      drive_client_id?: string | null;
      drive_client_secret?: string;
      drive_folder_id?: string | null;
    },
  ): Observable<ErpSettings> {
    return this.settingsApi.saveErpSettings(settings);
  }
  pushPreferences(): Observable<PushPreference[]> {
    return this.settingsApi.pushPreferences();
  }
  updatePushPreference(
    category: string,
    enabled: boolean,
    sound?: PushSound,
  ): Observable<PushPreference> {
    return this.settingsApi.updatePushPreference(category, enabled, sound);
  }
  pushHistory(): Observable<PushNotification[]> {
    return this.settingsApi.pushHistory();
  }
  connectGoogleDrive(): Observable<{ authorization_url: string; redirect_uri: string }> {
    return this.settingsApi.connectGoogleDrive();
  }
  runGoogleDriveBackup(): Observable<{ filename: string; message: string }> {
    return this.settingsApi.runGoogleDriveBackup();
  }
  dashboard(startDate: string, endDate: string): Observable<DashboardSummary> {
    return this.dashboardApi.dashboard(startDate, endDate);
  }
  dashboardFinancial(startDate: string, endDate: string): Observable<DashboardFinancialMetrics> {
    return this.dashboardApi.dashboardFinancial(startDate, endDate);
  }
  financeOverview(startDate: string, endDate: string): Observable<FinanceOverview> {
    return this.dashboardApi.financeOverview(startDate, endDate);
  }
  products(
    search = '',
    lowStock = false,
    stockType?: 'product' | 'warehouse',
  ): Observable<Product[]> {
    return this.productsApi.products(search, lowStock, stockType);
  }
  productMovements(id: string): Observable<import('./models').StockMovement[]> {
    return this.productsApi.productMovements(id);
  }
  productDetail(id: string): Observable<ProductDetail> {
    return this.productsApi.productDetail(id);
  }
  syncMarketplaceStock(id: string): Observable<Product> {
    return this.productsApi.syncMarketplaceStock(id);
  }
  createProduct(payload: Partial<Product>): Observable<Product> {
    return this.productsApi.createProduct(payload);
  }
  updateProduct(id: string, payload: Partial<Product>): Observable<Product> {
    return this.productsApi.updateProduct(id, payload);
  }
  uploadProductImages(id: string, files: File[]): Observable<Product> {
    return this.productsApi.uploadProductImages(id, files);
  }
  deleteProductImage(id: string, imageId: string): Observable<Product> {
    return this.productsApi.deleteProductImage(id, imageId);
  }
  productChannelMetadata(
    provider: 'mercadolivre' | 'shopee',
    query = '',
    categoryId = '',
  ): Observable<ProductChannelMetadata> {
    return this.productsApi.productChannelMetadata(provider, query, categoryId);
  }
  saveProductChannelDraft(
    id: string,
    provider: 'mercadolivre' | 'shopee',
    draft: ProductChannelDraft,
  ): Observable<ProductDetail> {
    return this.productsApi.saveProductChannelDraft(id, provider, draft);
  }
  publishProductChannel(
    id: string,
    provider: 'mercadolivre' | 'shopee',
  ): Observable<ProductDetail> {
    return this.productsApi.publishProductChannel(id, provider);
  }
  adjustStock(id: string, quantity: number, reason: string): Observable<Product> {
    return this.productsApi.adjustStock(id, quantity, reason);
  }
  purchases(params?: {
    limit?: number;
    offset?: number;
    search?: string;
    status?: string;
    startDate?: string;
    endDate?: string;
  }): Observable<PurchaseListOut> {
    return this.purchasesApi.purchases(params);
  }
  purchase(id: string): Observable<Purchase> {
    return this.purchasesApi.purchase(id);
  }
  createPurchase(payload: unknown): Observable<Purchase> {
    return this.purchasesApi.createPurchase(payload);
  }
  addPurchaseQuote(id: string, payload: unknown): Observable<Purchase> {
    return this.purchasesApi.addPurchaseQuote(id, payload);
  }
  selectPurchaseQuote(id: string, quoteId: string): Observable<Purchase> {
    return this.purchasesApi.selectPurchaseQuote(id, quoteId);
  }
  placePurchaseOrder(id: string): Observable<Purchase> {
    return this.purchasesApi.placePurchaseOrder(id);
  }
  receivePurchase(id: string, payload: unknown): Observable<Purchase> {
    return this.purchasesApi.receivePurchase(id, payload);
  }
  cancelPurchase(id: string): Observable<Purchase> {
    return this.purchasesApi.cancelPurchase(id);
  }
  cancelPurchaseWithReason(
    id: string,
    payload: { reason: string; resolution?: string; return_items?: unknown[] },
  ): Observable<Purchase> {
    return this.purchasesApi.cancelPurchaseWithReason(id, payload);
  }
  closePurchaseBalance(id: string, payload: { reason?: string | null }): Observable<Purchase> {
    return this.purchasesApi.closePurchaseBalance(id, payload);
  }
  deletePurchase(
    id: string,
    reason?: string,
  ): Observable<{ number: string; items_summary: string }> {
    return this.purchasesApi.deletePurchase(id, reason);
  }
  updatePurchase(id: string, payload: unknown): Observable<Purchase> {
    return this.purchasesApi.updatePurchase(id, payload);
  }
  addPurchaseItem(id: string, payload: unknown): Observable<Purchase> {
    return this.purchasesApi.addPurchaseItem(id, payload);
  }
  removePurchaseItem(id: string, itemId: string): Observable<Purchase> {
    return this.purchasesApi.removePurchaseItem(id, itemId);
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
    return this.purchasesApi.suppliers();
  }
  createSupplier(payload: unknown): Observable<{
    id: string;
    name: string;
    default_delivery_days: number | null;
    default_payment_terms: string | null;
  }> {
    return this.purchasesApi.createSupplier(payload);
  }
  receivePurchaseInFull(
    id: string,
    options?: { create_products?: boolean; observation?: string },
  ): Observable<Purchase> {
    return this.purchasesApi.receivePurchaseInFull(id, options);
  }
  settlePurchasePayable(
    purchaseId: string,
    payableId: string,
    payload: unknown = {},
  ): Observable<unknown> {
    return this.purchasesApi.settlePurchasePayable(purchaseId, payableId, payload);
  }
  payables(
    params: Record<string, string | number | boolean> = {},
  ): Observable<PayableListResponse> {
    return this.payablesApi.payables(params);
  }
  payable(id: string): Observable<PayableDetail> {
    return this.payablesApi.payable(id);
  }
  payableReport(params: Record<string, string | number | boolean> = {}): Observable<PayableReport> {
    return this.payablesApi.payableReport(params);
  }
  addPayablePayment(id: string, payload: unknown): Observable<PayableDetail> {
    return this.payablesApi.addPayablePayment(id, payload);
  }
  removePayablePayment(id: string, paymentId: string): Observable<PayableDetail> {
    return this.payablesApi.removePayablePayment(id, paymentId);
  }
  reconcilePayablePayment(
    id: string,
    paymentId: string,
    reconciled: boolean,
  ): Observable<PayableDetail> {
    return this.payablesApi.reconcilePayablePayment(id, paymentId, reconciled);
  }
  updatePayable(id: string, payload: unknown): Observable<PayableDetail> {
    return this.payablesApi.updatePayable(id, payload);
  }
  downloadPayablesCsv(params: Record<string, string | number | boolean> = {}): void {
    this.payablesApi.downloadPayablesCsv(params);
  }
  updatePurchasePayable(
    purchaseId: string,
    payableId: string,
    payload: unknown,
  ): Observable<unknown> {
    return this.purchasesApi.updatePurchasePayable(purchaseId, payableId, payload);
  }
  updatePurchaseItem(id: string, itemId: string, payload: unknown): Observable<Purchase> {
    return this.purchasesApi.updatePurchaseItem(id, itemId, payload);
  }
  uploadPurchaseAttachments(id: string, files: File[]): Observable<Purchase> {
    return this.purchasesApi.uploadPurchaseAttachments(id, files);
  }
  downloadPurchaseAttachment(id: string, attachmentId: string, filename: string): void {
    this.purchasesApi.downloadPurchaseAttachment(id, attachmentId, filename);
  }
  customers(): Observable<Customer[]> {
    return this.customersApi.customers();
  }
  customerDetail(id: string): Observable<CustomerDetail> {
    return this.customersApi.customerDetail(id);
  }
  createCustomer(payload: Partial<Customer>): Observable<Customer> {
    return this.customersApi.createCustomer(payload);
  }
  users(): Observable<User[]> {
    return this.usersApi.users();
  }
  createUser(payload: {
    email: string;
    full_name: string;
    password: string;
    role: User['role'];
  }): Observable<User> {
    return this.usersApi.createUser(payload);
  }
  resetUserPassword(id: string, password: string): Observable<User> {
    return this.usersApi.resetUserPassword(id, password);
  }
  updateUser(
    id: string,
    payload: {
      email?: string;
      full_name?: string;
      password?: string;
      role?: User['role'];
      active?: boolean;
    },
  ): Observable<User> {
    return this.usersApi.updateUser(id, payload);
  }
  updateMyProfile(email: string): Observable<User> {
    return this.usersApi.updateMyProfile(email);
  }
  uploadMyAvatar(file: File): Observable<User> {
    return this.usersApi.uploadMyAvatar(file);
  }
  myAvatar(): Observable<Blob> {
    return this.usersApi.myAvatar();
  }
  automateMarketplaceOrder(id: string): Observable<MarketplaceOrder> {
    return this.marketplaceApi.automateMarketplaceOrder(id);
  }
  requestMarketplaceInvoice(id: string): Observable<MarketplaceOrder> {
    return this.marketplaceApi.requestMarketplaceInvoice(id);
  }
  retryMarketplaceLabel(id: string): Observable<MarketplaceOrder> {
    return this.marketplaceApi.retryMarketplaceLabel(id);
  }
  invoices(startDate: string, endDate: string): Observable<Invoice[]> {
    return this.invoicesApi.invoices(startDate, endDate);
  }
  invoice(id: string): Observable<Invoice> {
    return this.invoicesApi.invoice(id);
  }
  receiveAfterSale(
    caseId: string,
    items: { item_id: string; received_quantity: number }[],
    notes?: string,
  ): Observable<AfterSaleCase> {
    return this.invoicesApi.receiveAfterSale(caseId, items, notes);
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
    return this.invoicesApi.inspectAfterSale(caseId, items);
  }
  closeAfterSaleWithoutStock(caseId: string, note: string): Observable<AfterSaleCase> {
    return this.invoicesApi.closeAfterSaleWithoutStock(caseId, note);
  }
  createInvoice(payload: unknown): Observable<Invoice> {
    return this.invoicesApi.createInvoice(payload);
  }
  confirmInvoice(id: string): Observable<Invoice> {
    return this.invoicesApi.confirmInvoice(id);
  }
  cancelInvoice(id: string): Observable<Invoice> {
    return this.invoicesApi.cancelInvoice(id);
  }
  downloadInvoiceDocument(invoiceId: string, documentId: string): Observable<Blob> {
    return this.invoicesApi.downloadInvoiceDocument(invoiceId, documentId);
  }
  invoiceDocumentBrowserUrl(invoiceId: string, documentId: string): Observable<{ url: string }> {
    return this.invoicesApi.invoiceDocumentBrowserUrl(invoiceId, documentId);
  }
  marketplaceStatus(): Observable<MarketplaceStatus> {
    return this.marketplaceApi.marketplaceStatus();
  }
  marketplaceConfig(): Observable<MarketplaceConfig> {
    return this.marketplaceApi.marketplaceConfig();
  }
  saveMarketplaceConfig(payload: Record<string, unknown>): Observable<MarketplaceConfig> {
    return this.marketplaceApi.saveMarketplaceConfig(payload);
  }
  marketplaceOrders(): Observable<MarketplaceOrder[]> {
    return this.marketplaceApi.marketplaceOrders();
  }
  marketplaceOrder(id: string): Observable<MarketplaceOrder> {
    return this.marketplaceApi.marketplaceOrder(id);
  }
  marketplaceOrderHistory(id: string): Observable<MarketplaceOrderEvent[]> {
    return this.marketplaceApi.marketplaceOrderHistory(id);
  }
  syncMarketplace(): Observable<{ accepted: boolean; message: string }> {
    return this.marketplaceApi.syncMarketplace();
  }
  connectMarketplace(): Observable<{ authorization_url: string }> {
    return this.marketplaceApi.connectMarketplace();
  }
  shopeeStatus(): Observable<ShopeeStatus> {
    return this.marketplaceApi.shopeeStatus();
  }
  shopeeConfig(): Observable<ShopeeConfig> {
    return this.marketplaceApi.shopeeConfig();
  }
  saveShopeeConfig(payload: Record<string, unknown>): Observable<ShopeeConfig> {
    return this.marketplaceApi.saveShopeeConfig(payload);
  }
  connectShopee(): Observable<{ authorization_url: string }> {
    return this.marketplaceApi.connectShopee();
  }
  telemetrySummary(startDate: string, endDate: string): Observable<TelemetrySummary> {
    return this.integrationsApi.telemetrySummary(startDate, endDate);
  }
}
