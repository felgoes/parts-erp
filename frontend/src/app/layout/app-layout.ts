import { DatePipe } from '@angular/common';
import { Component, DestroyRef, OnDestroy, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { RouterLink, RouterOutlet } from '@angular/router';
import { debounceTime } from 'rxjs';
import { AppearanceService } from '../core/appearance.service';
import { ErpBrandService } from '../core/erp-brand.service';
import { AuthService } from '../core/auth.service';
import { ApiService } from '../core/api.service';
import { ROLE_LABELS } from '../core/user-access';
import { PushNotificationsService } from '../core/push-notifications.service';
import { LiveUpdatesService } from '../core/live-updates.service';
import { PULL_TRIGGER_PX, pullBandHeight, pullOffset, shouldRefresh } from '../core/app-refresh';
import { BackupAlert, backupAlert as buildBackupAlert } from '../shared/backup-health';
import { SettingsApi } from '../core/api/settings-api';
import { PushNotification } from '../core/models';
import { AssistantChat } from '../shared/assistant-chat/assistant-chat';
import { NavigationMenu } from './navigation-menu/navigation-menu';
import { NotificationsMenu } from './notifications-menu/notifications-menu';

@Component({
  selector: 'app-layout',
  imports: [
    DatePipe,
    RouterOutlet,
    RouterLink,
    ReactiveFormsModule,
    AssistantChat,
    NavigationMenu,
    NotificationsMenu,
  ],
  templateUrl: './app-layout.html',
  styleUrl: './app-layout.scss',
})
export class AppLayout implements OnInit, OnDestroy {
  readonly auth = inject(AuthService);
  readonly brand = inject(ErpBrandService);
  readonly appearance = inject(AppearanceService);
  readonly live = inject(LiveUpdatesService);
  readonly menuOpen = signal(false);
  readonly profileOpen = signal(false);
  readonly avatarUrl = signal<string | null>(null);
  readonly previewUrl = signal<string | null>(null);
  readonly selectedAvatar = signal<File | null>(null);
  readonly profileMessage = signal('');
  readonly profileSaving = signal(false);
  readonly avatarSaving = signal(false);
  readonly backupAlert = signal<BackupAlert | null>(null);
  readonly vehicleUpdate = signal<PushNotification | null>(null);
  /** Faixa do gesto: cresce com o dedo e fica de pé enquanto a tela recarrega. */
  readonly pullBand = computed(() => pullBandHeight(this.live.pullOffset()));
  readonly pullReady = computed(() => shouldRefresh(this.live.pullOffset()));
  readonly showPullBand = computed(() => this.pullBand() > 0 || this.live.refreshing());
  readonly canPull = computed(() => this.live.isAndroidApp());
  readonly lastUpdateLabel = computed(() => this.live.lastUpdateAt());
  private backupTimer: ReturnType<typeof setInterval> | null = null;
  private pullStartY = 0;
  private pulling = false;
  private readonly api = inject(ApiService);
  private readonly settingsApi = inject(SettingsApi);
  private readonly pushNotifications = inject(PushNotificationsService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly fb = inject(FormBuilder);
  readonly profileForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
  });
  ngOnInit(): void {
    this.brand.load();
    this.loadAvatar();
    this.loadBackupAlert();
    this.loadVehicleUpdateBanner();
    // O aviso de backup não depende de push: a faixa acompanha o estado do servidor.
    this.backupTimer = setInterval(() => {
      this.loadBackupAlert();
      this.loadVehicleUpdateBanner();
    }, 15 * 60 * 1000);
    this.live.changes$
      .pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.loadVehicleUpdateBanner());
    void this.pushNotifications.enableForCurrentDevice();
  }
  ngOnDestroy(): void {
    if (this.backupTimer !== null) clearInterval(this.backupTimer);
  }
  /**
   * Gesto de puxar para atualizar (P17). Só vale no aplicativo Android — no navegador do celular o
   * gesto é do próprio navegador e no desktop a tela já se atualiza sozinha — e só quando a tela
   * está no topo, para não disputar com a rolagem.
   */
  onTouchStart(event: TouchEvent): void {
    if (!this.canPull() || this.live.refreshing()) return;
    this.pullStartY = event.touches[0]?.clientY ?? 0;
    this.pulling = true;
  }

  onTouchMove(event: TouchEvent): void {
    if (!this.pulling) return;
    const offset = pullOffset(this.pullStartY, event.touches[0]?.clientY ?? 0, window.scrollY);
    if (offset <= 0) {
      this.live.pullOffset.set(0);
      return;
    }
    // Sem isto o WebView devolve o "elástico" e o gesto briga com a rolagem.
    if (offset > 4) event.preventDefault();
    this.live.pullOffset.set(offset);
  }

  onTouchEnd(): void {
    if (!this.pulling) return;
    this.pulling = false;
    const offset = this.live.pullOffset();
    this.live.pullOffset.set(0);
    if (offset >= PULL_TRIGGER_PX) this.live.refreshNow();
  }
  private loadBackupAlert(): void {
    // A faixa é para quem administra o ERP: administrador e gerente.
    const role = this.auth.user()?.role;
    if (role !== 'admin' && role !== 'manager') {
      this.backupAlert.set(null);
      return;
    }
    this.api.erpSettings().subscribe({
      next: (settings) => this.backupAlert.set(buildBackupAlert(settings)),
      error: () => undefined,
    });
  }

  private loadVehicleUpdateBanner(): void {
    this.api.pushHistory().subscribe({
      next: (items) =>
        this.vehicleUpdate.set(
          items.find((item) => item.category === 'vehicle_market') ?? null,
        ),
      error: () => undefined,
    });
  }

  dismissVehicleUpdate(): void {
    const notification = this.vehicleUpdate();
    if (!notification) return;
    this.settingsApi.dismissPushNotification(notification.id).subscribe({
      next: () => this.vehicleUpdate.set(null),
    });
  }
  openProfile(): void {
    const user = this.auth.user();
    if (!user) return;
    this.profileForm.setValue({ email: user.email });
    this.selectedAvatar.set(null);
    this.clearPreview();
    this.profileMessage.set('');
    this.profileOpen.set(true);
    this.loadAvatar();
  }
  closeProfile(): void {
    this.profileOpen.set(false);
    this.selectedAvatar.set(null);
    this.clearPreview();
  }
  saveProfile(): void {
    if (this.profileForm.invalid || this.profileSaving()) return;
    this.profileSaving.set(true);
    this.profileMessage.set('');
    this.api.updateMyProfile(this.profileForm.getRawValue().email.trim()).subscribe({
      next: (user) => {
        this.auth.updateCurrentUser(user);
        this.profileForm.setValue({ email: user.email });
        this.profileMessage.set('E-mail atualizado.');
        this.profileSaving.set(false);
      },
      error: (err) => {
        this.profileMessage.set(err?.error?.detail || 'Não foi possível atualizar o e-mail.');
        this.profileSaving.set(false);
      },
    });
  }
  selectAvatar(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    if (
      !['image/jpeg', 'image/png', 'image/webp'].includes(file.type) ||
      file.size > 5 * 1024 * 1024
    ) {
      this.profileMessage.set('Escolha uma imagem JPG, PNG ou WebP de até 5 MB.');
      return;
    }
    this.clearPreview();
    this.selectedAvatar.set(file);
    this.previewUrl.set(URL.createObjectURL(file));
    this.profileMessage.set('Confira a foto e salve para aplicar.');
  }
  saveAvatar(): void {
    const file = this.selectedAvatar();
    if (!file || this.avatarSaving()) return;
    this.avatarSaving.set(true);
    this.api.uploadMyAvatar(file).subscribe({
      next: () => {
        this.avatarSaving.set(false);
        this.selectedAvatar.set(null);
        this.clearPreview();
        this.profileMessage.set('Foto de perfil atualizada.');
        this.loadAvatar();
      },
      error: (err) => {
        this.avatarSaving.set(false);
        this.profileMessage.set(err?.error?.detail || 'Não foi possível enviar a foto.');
      },
    });
  }
  private loadAvatar(): void {
    this.api.myAvatar().subscribe({
      next: (blob) => {
        const previous = this.avatarUrl();
        if (previous) URL.revokeObjectURL(previous);
        this.avatarUrl.set(URL.createObjectURL(blob));
      },
      error: () => {
        const previous = this.avatarUrl();
        if (previous) URL.revokeObjectURL(previous);
        this.avatarUrl.set(null);
      },
    });
  }
  private clearPreview(): void {
    const preview = this.previewUrl();
    if (preview) URL.revokeObjectURL(preview);
    this.previewUrl.set(null);
  }
  get initials(): string {
    return (this.auth.user()?.full_name ?? 'U')
      .split(' ')
      .slice(0, 2)
      .map((x) => x[0])
      .join('')
      .toUpperCase();
  }
  get roleLabel(): string {
    return ROLE_LABELS[this.auth.user()?.role ?? 'operator'];
  }
}
