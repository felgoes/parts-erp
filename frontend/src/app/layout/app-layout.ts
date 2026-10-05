import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
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
        @for (item of nav; track item.path) {
          <a [routerLink]="item.path" routerLinkActive="active" (click)="menuOpen.set(false)"
            ><span class="nav-icon">{{ item.icon }}</span
            ><span>{{ item.label }}</span></a
          >
        }
        @if (auth.user()?.role === 'admin') { <a routerLink="/settings" routerLinkActive="active" (click)="menuOpen.set(false)"><span class="nav-icon">⚙</span><span>Configurações</span></a> }
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
  readonly menuOpen = signal(false);
  ngOnInit(): void {
    this.brand.load();
  }
  get nav() {
    const items = [
      { path: '/dashboard', label: 'Visão geral', icon: '◫' },
      { path: '/monitoring', label: 'Monitoramento', icon: 'O' },
      { path: '/products', label: 'Produtos e estoque', icon: '◇' },
      { path: '/purchases', label: 'Compras', icon: '↙' },
      { path: '/market-studies', label: 'Estudos de mercado', icon: '⌕' },
      { path: '/finance', label: 'Financeiro', icon: '$' },
      { path: '/invoices', label: 'Faturas de venda', icon: '▤' },
      { path: '/customers', label: 'Clientes', icon: '○' },
      { path: '/marketplace', label: 'Pedidos do ML', icon: 'M' },
      { path: '/integrations', label: 'Integrações', icon: '⌁' },
    ];
    const allItems = [...items, { path: '/users', label: 'Usuários', icon: '♙' }];
    return allItems.filter((item) => canAccessPage(this.auth.user()?.role, item.path));
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
