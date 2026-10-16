import { DatePipe } from '@angular/common';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { AppearanceService } from '../core/appearance.service';
import { ErpBrandService } from '../core/erp-brand.service';
import { AuthService } from '../core/auth.service';
import { ApiService } from '../core/api.service';
import { canAccessPage, ROLE_LABELS } from '../core/user-access';
import { PushNotification } from '../core/models';
import { PushNotificationsService } from '../core/push-notifications.service';
import { BackupAlert, backupAlert as buildBackupAlert } from '../shared/backup-health';

@Component({
  selector: 'app-layout',
  imports: [DatePipe, RouterOutlet, RouterLink, RouterLinkActive, ReactiveFormsModule],
  templateUrl: './app-layout.html',
  styleUrl: './app-layout.scss',
})
export class AppLayout implements OnInit, OnDestroy {
  readonly auth = inject(AuthService);
  readonly brand = inject(ErpBrandService);
  readonly appearance = inject(AppearanceService);
  private readonly router = inject(Router);
  readonly menuOpen = signal(false);
  readonly settingsOpen = signal(false);
  readonly profileOpen = signal(false);
  readonly avatarUrl = signal<string | null>(null);
  readonly previewUrl = signal<string | null>(null);
  readonly selectedAvatar = signal<File | null>(null);
  readonly profileMessage = signal('');
  readonly profileSaving = signal(false);
  readonly avatarSaving = signal(false);
  readonly notificationsOpen = signal(false);
  readonly notificationLoading = signal(false);
  readonly notificationHistory = signal<PushNotification[]>([]);
  readonly notificationCount = signal(0);
  readonly backupAlert = signal<BackupAlert | null>(null);
  private backupTimer: ReturnType<typeof setInterval> | null = null;
  private readonly api = inject(ApiService);
  private readonly pushNotifications = inject(PushNotificationsService);
  private readonly fb = inject(FormBuilder);
  readonly profileForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
  });
  ngOnInit(): void {
    this.brand.load();
    this.loadAvatar();
    this.loadNotifications();
    this.loadBackupAlert();
    // O aviso de backup não depende de push: a faixa acompanha o estado do servidor.
    this.backupTimer = setInterval(() => this.loadBackupAlert(), 15 * 60 * 1000);
    void this.pushNotifications.enableForCurrentDevice();
    this.settingsOpen.set(this.isConfigurationRoute());
    this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => {
        const route = event.urlAfterRedirects.split('?')[0].replace(/^\//, '');
        this.settingsOpen.set(['settings', 'integrations', 'users'].includes(route));
        this.notificationsOpen.set(false);
      });
  }
  ngOnDestroy(): void {
    if (this.backupTimer !== null) clearInterval(this.backupTimer);
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
  notificationPreview(): PushNotification[] {
    return this.notificationHistory().slice(0, 4);
  }
  toggleNotifications(): void {
    const open = !this.notificationsOpen();
    this.notificationsOpen.set(open);
    if (open) {
      this.loadNotifications();
      this.markNotificationsSeen();
    }
  }
  private loadNotifications(): void {
    this.notificationLoading.set(true);
    this.api.pushHistory().subscribe({
      next: (items) => {
        this.notificationHistory.set(items);
        const seenAt = this.notificationsSeenAt();
        this.notificationCount.set(
          items.filter((item) => !seenAt || item.created_at > seenAt).length,
        );
      },
      error: () => this.notificationHistory.set([]),
      complete: () => this.notificationLoading.set(false),
    });
  }
  private notificationsSeenAt(): string | null {
    const userId = this.auth.user()?.id;
    return userId ? localStorage.getItem(`parts-erp.notifications.seen.${userId}`) : null;
  }
  private markNotificationsSeen(): void {
    const userId = this.auth.user()?.id;
    const latest = this.notificationHistory()[0]?.created_at;
    if (userId && latest) localStorage.setItem(`parts-erp.notifications.seen.${userId}`, latest);
    this.notificationCount.set(0);
  }
  get navigationSections() {
    const role = this.auth.user()?.role;
    const sections = [
      {
        label: 'Operação',
        items: [
          { path: '/marketplace', label: 'Pedidos do ML', icon: 'M' },
          { path: '/invoices', label: 'Faturas de venda', icon: '▤' },
          { path: '/products', label: 'Produtos e estoque', icon: '◇' },
          { path: '/purchases', label: 'Compras', icon: '↙' },
          { path: '/customers', label: 'Clientes', icon: '○' },
        ],
      },
      {
        label: 'Análise',
        items: [
          { path: '/monitoring', label: 'Monitoramento', icon: '◉' },
          { path: '/finance', label: 'Financeiro', icon: '$' },
          { path: '/payables', label: 'Contas a pagar', icon: '↧' },
          { path: '/market-studies', label: 'Estudos de mercado', icon: '⌕' },
        ],
      },
    ];
    return sections.map((section) => ({
      ...section,
      items: section.items.filter((item) => canAccessPage(role, item.path)),
    }));
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
  isConfigurationRoute(): boolean {
    const route = this.router.url.split('?')[0].replace(/^\//, '');
    return ['settings', 'integrations', 'users'].includes(route);
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
