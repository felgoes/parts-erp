import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AppearanceService, AppearanceTheme } from '../../core/appearance.service';
import { ErpBrandService } from '../../core/erp-brand.service';
import { ErpSettings } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-settings',
  imports: [FormsModule, PageHeader, DatePipe],
  templateUrl: './settings.html',
  styleUrl: './settings.scss',
})
export class SettingsPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly appearance = inject(AppearanceService);
  private readonly brand = inject(ErpBrandService);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly driveConnecting = signal(false);
  readonly backupRunning = signal(false);
  readonly message = signal('');
  readonly error = signal('');
  readonly logoError = signal('');
  readonly importProfiles = signal<Array<{ profile_id: string; name: string; kind: string; version: number }>>([]);
  readonly profileBusy = signal(false);
  readonly profileError = signal('');
  readonly settings = signal<ErpSettings>({
    company_name: 'Parts ERP',
    company_short_name: 'Parts',
    logo_data_url: null,
    backup_enabled: false,
    backup_frequency: 'daily',
    backup_time: '02:00',
    backup_retention_days: 30,
    backup_destination: 'google_drive',
    backup_ready: false,
    backup_status: 'setup_required',
    drive_client_id: null,
    drive_client_secret_configured: false,
    drive_folder_id: null,
    drive_connected: false,
    backup_last_at: null,
    backup_last_status: 'setup_required',
    backup_last_error: null,
  });
  readonly draft = {
    company_name: 'Parts ERP',
    company_short_name: 'Parts',
    logo_data_url: null as string | null,
    backup_enabled: false,
    backup_frequency: 'daily' as 'daily' | 'weekly',
    backup_time: '02:00',
    backup_retention_days: 30,
    backup_destination: 'google_drive' as const,
    drive_client_id: '',
    drive_client_secret: '',
    drive_folder_id: '',
  };

  ngOnInit(): void {
    const params = new URLSearchParams(window.location.search);
    if (params.get('drive_connected') === 'true') this.message.set('Google Drive conectado. Salve a política de backup para ativá-la.');
    if (params.get('drive_error')) this.error.set('Não foi possível autorizar o Google Drive. Confira o Client ID, o segredo e o redirect URI.');
    if (params.has('drive_connected') || params.has('drive_error')) window.history.replaceState({}, '', window.location.pathname);
    this.api.purchaseImportProfiles().subscribe({ next: (result) => this.importProfiles.set(result.profiles), error: () => undefined });
    this.api.erpSettings().pipe(finalize(() => this.loading.set(false))).subscribe({
      next: (settings) => this.applySettings(settings),
      error: () => this.error.set('Não foi possível carregar as configurações. Tente novamente.'),
    });
  }

  uploadImportProfile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.profileError.set('');
    this.profileBusy.set(true);
    this.api.uploadPurchaseImportProfile(file).pipe(finalize(() => this.profileBusy.set(false))).subscribe({
      next: (result) => {
        this.message.set(`Perfil ${result.name} importado.`);
        this.api.purchaseImportProfiles().subscribe((response) => this.importProfiles.set(response.profiles));
      },
      error: (err) => this.profileError.set(err?.error?.detail || 'Não foi possível importar este perfil JSON.'),
    });
  }

  deleteImportProfile(profileId: string): void {
    if (this.profileBusy()) return;
    this.profileBusy.set(true);
    this.api.deletePurchaseImportProfile(profileId).pipe(finalize(() => this.profileBusy.set(false))).subscribe({
      next: () => {
        this.importProfiles.update((profiles) => profiles.filter((item) => item.profile_id !== profileId));
        this.message.set('Perfil removido.');
      },
      error: (err) => this.profileError.set(err?.error?.detail || 'Não foi possível remover o perfil.'),
    });
  }

  downloadImportProfileExample(): void {
    const example = {
      schema: 'parts-erp-purchase-import-profile/v1',
      profile_id: 'loja_exemplo',
      name: 'Minha loja',
      version: 1,
      match_terms: ['Minha loja', 'Order details'],
      field_labels: {
        supplier: ['Seller', 'Vendido por'],
        order_number: ['Order number', 'Pedido nº'],
        total: ['Order total', 'Total pago'],
      },
    };
    const blob = new Blob([JSON.stringify(example, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url; link.download = 'perfil-importacao-exemplo.json'; link.click();
    URL.revokeObjectURL(url);
  }

  chooseTheme(theme: AppearanceTheme): void {
    this.appearance.setTheme(theme);
  }

  selectLogo(event: Event): void {
    this.logoError.set('');
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    if (!['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || file.size > 2 * 1024 * 1024) {
      this.logoError.set('Use um arquivo PNG, JPEG ou WebP de até 2 MB.');
      input.value = '';
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      this.draft.logo_data_url = String(reader.result);
    };
    reader.onerror = () => this.logoError.set('Não foi possível ler esse arquivo.');
    reader.readAsDataURL(file);
  }

  removeLogo(): void {
    this.draft.logo_data_url = null;
  }

  save(): void {
    this.message.set('');
    this.error.set('');
    this.saving.set(true);
    this.api.saveErpSettings(this.draft).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (settings) => {
        this.applySettings(settings);
        this.brand.apply(settings);
        this.message.set('Configurações salvas. A identidade da empresa será aplicada no sistema.');
      },
      error: (err) => this.error.set(err?.error?.detail || 'Não foi possível salvar as configurações.'),
    });
  }

  connectGoogleDrive(): void {
    this.driveConnecting.set(true);
    this.api.connectGoogleDrive().subscribe({
      next: ({ authorization_url }) => window.location.assign(authorization_url),
      error: (err) => { this.error.set(err?.error?.detail || 'Informe as credenciais OAuth do Google Drive e salve primeiro.'); this.driveConnecting.set(false); },
    });
  }

  runBackup(): void {
    this.backupRunning.set(true);
    this.message.set('');
    this.error.set('');
    this.api.runGoogleDriveBackup().subscribe({
      next: (result) => { this.message.set(result.message); this.backupRunning.set(false); this.api.erpSettings().subscribe((settings) => this.applySettings(settings)); },
      error: (err) => { this.error.set(err?.error?.detail || 'Não foi possível concluir o backup.'); this.backupRunning.set(false); },
    });
  }

  private applySettings(settings: ErpSettings): void {
    this.settings.set(settings);
    Object.assign(this.draft, {
      company_name: settings.company_name,
      company_short_name: settings.company_short_name,
      logo_data_url: settings.logo_data_url,
      backup_enabled: settings.backup_enabled,
      backup_frequency: settings.backup_frequency,
      backup_time: settings.backup_time,
      backup_retention_days: settings.backup_retention_days,
      backup_destination: settings.backup_destination,
      drive_client_id: settings.drive_client_id || '',
      drive_client_secret: '',
      drive_folder_id: settings.drive_folder_id || '',
    });
  }
}
