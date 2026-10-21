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
export class SettingsApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('');
  erpSettings(): Observable<ErpSettings> {
    return this.http.get<ErpSettings>(`${this.base}/settings`);
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
    return this.http.put<ErpSettings>(`${this.base}/settings`, settings);
  }
  pushPreferences(): Observable<PushPreference[]> {
    return this.http.get<PushPreference[]>(`${this.base}/push/preferences`);
  }
  updatePushPreference(
    category: string,
    enabled: boolean,
    sound?: PushSound,
  ): Observable<PushPreference> {
    return this.http.put<PushPreference>(this.base + '/push/preferences/' + category, {
      enabled,
      sound,
    });
  }
  pushHistory(): Observable<PushNotification[]> {
    return this.http.get<PushNotification[]>(`${this.base}/push/history`);
  }
  dismissPushNotification(id: string): Observable<void> {
    return this.http.delete<void>(this.base + '/push/history/' + encodeURIComponent(id));
  }
  connectGoogleDrive(): Observable<{ authorization_url: string; redirect_uri: string }> {
    return this.http.get<{ authorization_url: string; redirect_uri: string }>(
      `${this.base}/settings/backup/google-drive/connect`,
    );
  }
  runGoogleDriveBackup(): Observable<{ filename: string; message: string }> {
    return this.http.post<{ filename: string; message: string }>(
      `${this.base}/settings/backup/run`,
      {},
    );
  }
}
