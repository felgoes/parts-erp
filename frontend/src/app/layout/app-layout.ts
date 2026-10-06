import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { AppearanceService } from '../core/appearance.service';
import { ErpBrandService } from '../core/erp-brand.service';
import { AuthService } from '../core/auth.service';
import { ApiService } from '../core/api.service';
import { canAccessPage, ROLE_LABELS } from '../core/user-access';

@Component({
  selector: 'app-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive, ReactiveFormsModule],
  template: ` <div class="app-shell" [class.menu-open]="menuOpen()">
    <aside class="sidebar">
      <div class="brand">
        @if (brand.logo()) { <img class="brand-logo" [src]="brand.logo()" alt="" /> } @else { <span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" focusable="false"><path d="M12 36V12h13c7 0 11 3 11 9s-4 9-11 9H18" /><path d="M25 30l9-9" /></svg></span> }
        <div><strong>{{ brand.shortName() }}</strong><small>{{ brand.suffix() }}</small></div>
      </div>
      <nav aria-label="Menu principal">
        <a class="overview-link" routerLink="/dashboard" routerLinkActive="active" (click)="menuOpen.set(false)">
          <span class="nav-icon">◫</span><span>Visão geral</span>
        </a>
        @for (section of navigationSections; track section.label) {
          @if (section.items.length) {
            <div class="nav-section">
              <p class="nav-section-label">{{ section.label }}</p>
              @for (item of section.items; track item.path) {
                <a [routerLink]="item.path" routerLinkActive="active" (click)="menuOpen.set(false)">
                  <span class="nav-icon">{{ item.icon }}</span><span>{{ item.label }}</span>
                </a>
              }
            </div>
          }
        }
        @if (auth.user()?.role === 'admin') {
          <div class="nav-section configuration-section">
            <button class="configuration-toggle" type="button" [class.active]="isConfigurationRoute()"
              [attr.aria-expanded]="settingsOpen()" (click)="settingsOpen.set(!settingsOpen())">
              <span class="nav-icon">⚙</span><span>Configurações</span><span class="nav-chevron" aria-hidden="true">⌄</span>
            </button>
            @if (settingsOpen()) {
              <div class="nav-children">
                <a routerLink="/settings" routerLinkActive="active" (click)="menuOpen.set(false)">Geral</a>
                <a routerLink="/integrations" routerLinkActive="active" (click)="menuOpen.set(false)">Integrações</a>
                <a routerLink="/users" routerLinkActive="active" (click)="menuOpen.set(false)">Usuários</a>
              </div>
            }
          </div>
        }
      </nav>
      <div class="sidebar-foot">
        <button class="profile-trigger" type="button" aria-label="Abrir meu perfil" (click)="openProfile()">
          @if (avatarUrl(); as photo) { <img class="avatar" [src]="photo" alt="" /> } @else { <span class="avatar">{{ initials }}</span> }
          <span class="profile-copy"><strong>{{ auth.user()?.full_name }}</strong><small>Meu perfil · {{ roleLabel }}</small></span>
          <span class="profile-chevron" aria-hidden="true">›</span>
        </button>
        <button class="icon-button" title="Sair" aria-label="Sair" (click)="auth.logout()">↗</button>
      </div>
    </aside>
    <div class="mobile-bar">
      <button class="icon-button" aria-label="Abrir menu" (click)="menuOpen.set(!menuOpen())">
        ☰
      </button>
      <div class="brand">@if (brand.logo()) { <img class="brand-logo" [src]="brand.logo()" alt="" /> } @else { <span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" focusable="false"><path d="M12 36V12h13c7 0 11 3 11 9s-4 9-11 9H18" /><path d="M25 30l9-9" /></svg></span> }<strong>{{ brand.shortName() }} {{ brand.suffix() }}</strong></div>
    </div>
    <button class="scrim" aria-label="Fechar menu" (click)="menuOpen.set(false)"></button>
    @if (profileOpen()) {
      <div class="profile-backdrop" (click)="closeProfile()">
        <section class="profile-dialog" role="dialog" aria-modal="true" aria-labelledby="profile-title" (click)="$event.stopPropagation()">
          <header class="profile-dialog-head"><div><p class="eyebrow">Minha conta</p><h2 id="profile-title">Meu perfil</h2></div><button class="profile-close" type="button" aria-label="Fechar perfil" (click)="closeProfile()">×</button></header>
          @if (profileMessage()) { <p class="profile-message" role="status">{{ profileMessage() }}</p> }
          <div class="profile-photo-block">
            @if (previewUrl() || avatarUrl(); as photo) { <img class="profile-photo" [src]="photo" alt="Foto do perfil" /> } @else { <span class="profile-photo profile-photo-initials">{{ initials }}</span> }
            <div><strong>Foto de perfil</strong><small>JPG, PNG ou WebP · até 5 MB</small><label class="profile-photo-button">{{ avatarSaving() ? 'Enviando…' : 'Escolher foto' }}<input type="file" accept="image/jpeg,image/png,image/webp" (change)="selectAvatar($event)" /></label></div>
          </div>
          @if (selectedAvatar()) { <button class="profile-save-photo" type="button" [disabled]="avatarSaving()" (click)="saveAvatar()">{{ avatarSaving() ? 'Salvando foto…' : 'Salvar foto' }}</button> }
          <form class="profile-form" [formGroup]="profileForm" (ngSubmit)="saveProfile()">
            <label for="profile-email">E-mail</label><input id="profile-email" type="email" formControlName="email" autocomplete="email" required />
            <button class="profile-save" type="submit" [disabled]="profileForm.invalid || profileSaving()">{{ profileSaving() ? 'Salvando…' : 'Salvar e-mail' }}</button>
          </form>
        </section>
      </div>
    }
    <main><router-outlet /></main>
  </div>`,
  styleUrl: './app-layout.scss',
})
export class AppLayout implements OnInit {
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
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly profileForm = this.fb.nonNullable.group({ email: ['', [Validators.required, Validators.email]] });
  ngOnInit(): void {
    this.brand.load();
    this.loadAvatar();
    this.settingsOpen.set(this.isConfigurationRoute());
    this.router.events.pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => {
        const route = event.urlAfterRedirects.split('?')[0].replace(/^\//, '');
        this.settingsOpen.set(['settings', 'integrations', 'users'].includes(route));
      });
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
      next: (user) => { this.auth.updateCurrentUser(user); this.profileForm.setValue({ email: user.email }); this.profileMessage.set('E-mail atualizado.'); this.profileSaving.set(false); },
      error: (err) => { this.profileMessage.set(err?.error?.detail || 'Não foi possível atualizar o e-mail.'); this.profileSaving.set(false); },
    });
  }
  selectAvatar(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type) || file.size > 5 * 1024 * 1024) {
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
      next: () => { this.avatarSaving.set(false); this.selectedAvatar.set(null); this.clearPreview(); this.profileMessage.set('Foto de perfil atualizada.'); this.loadAvatar(); },
      error: (err) => { this.avatarSaving.set(false); this.profileMessage.set(err?.error?.detail || 'Não foi possível enviar a foto.'); },
    });
  }
  private loadAvatar(): void {
    this.api.myAvatar().subscribe({
      next: (blob) => { const previous = this.avatarUrl(); if (previous) URL.revokeObjectURL(previous); this.avatarUrl.set(URL.createObjectURL(blob)); },
      error: () => { const previous = this.avatarUrl(); if (previous) URL.revokeObjectURL(previous); this.avatarUrl.set(null); },
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
