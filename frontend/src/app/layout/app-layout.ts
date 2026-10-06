import { Component, OnInit, inject, signal } from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AppearanceService } from '../core/appearance.service';
import { ErpBrandService } from '../core/erp-brand.service';
import { AuthService } from '../core/auth.service';
import { canAccessPage, ROLE_LABELS } from '../core/user-access';

@Component({
  selector: 'app-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
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
              [attr.aria-expanded]="configurationOpen" (click)="settingsOpen.set(!settingsOpen())">
              <span class="nav-icon">⚙</span><span>Configurações</span><span class="nav-chevron" aria-hidden="true">⌄</span>
            </button>
            @if (configurationOpen) {
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
        <span class="avatar">{{ initials }}</span>
        <div>
          <strong>{{ auth.user()?.full_name }}</strong
          ><small>{{ roleLabel }}</small>
        </div>
        <button class="icon-button" title="Sair" aria-label="Sair" (click)="auth.logout()">
          ↗
        </button>
      </div>
    </aside>
    <div class="mobile-bar">
      <button class="icon-button" aria-label="Abrir menu" (click)="menuOpen.set(!menuOpen())">
        ☰
      </button>
      <div class="brand">@if (brand.logo()) { <img class="brand-logo" [src]="brand.logo()" alt="" /> } @else { <span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" focusable="false"><path d="M12 36V12h13c7 0 11 3 11 9s-4 9-11 9H18" /><path d="M25 30l9-9" /></svg></span> }<strong>{{ brand.shortName() }} {{ brand.suffix() }}</strong></div>
    </div>
    <button class="scrim" aria-label="Fechar menu" (click)="menuOpen.set(false)"></button>
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
  ngOnInit(): void {
    this.brand.load();
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
  get configurationOpen(): boolean {
    const route = this.router.url.split('?')[0].replace(/^\//, '');
    return this.settingsOpen() || ['settings', 'integrations', 'users'].includes(route);
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
