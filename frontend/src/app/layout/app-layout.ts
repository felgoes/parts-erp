import { Component, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../core/auth.service';

@Component({
  selector: 'app-layout',
  imports: [RouterOutlet, RouterLink, RouterLinkActive],
  template: ` <div class="app-shell" [class.menu-open]="menuOpen()">
    <aside class="sidebar">
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" focusable="false"><path d="M12 36V12h13c7 0 11 3 11 9s-4 9-11 9H18" /><path d="M25 30l9-9" /></svg></span>
        <div><strong>Parts</strong><small>ERP</small></div>
      </div>
      <nav aria-label="Menu principal">
        @for (item of nav; track item.path) {
          <a [routerLink]="item.path" routerLinkActive="active" (click)="menuOpen.set(false)"
            ><span class="nav-icon">{{ item.icon }}</span
            ><span>{{ item.label }}</span></a
          >
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
      <div class="brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" focusable="false"><path d="M12 36V12h13c7 0 11 3 11 9s-4 9-11 9H18" /><path d="M25 30l9-9" /></svg></span><strong>Parts ERP</strong></div>
    </div>
    <button class="scrim" aria-label="Fechar menu" (click)="menuOpen.set(false)"></button>
    <main><router-outlet /></main>
  </div>`,
  styleUrl: './app-layout.scss',
})
export class AppLayout {
  readonly auth = inject(AuthService);
  readonly menuOpen = signal(false);
  get nav() {
    const items = [
      { path: '/dashboard', label: 'Visão geral', icon: '◫' },
      { path: '/monitoring', label: 'Monitoramento', icon: 'O' },
      { path: '/products', label: 'Produtos e estoque', icon: '◇' },
      { path: '/invoices', label: 'Faturas de venda', icon: '▤' },
      { path: '/customers', label: 'Clientes', icon: '○' },
      { path: '/marketplace', label: 'Pedidos do ML', icon: 'M' },
      { path: '/integrations', label: 'Integrações', icon: '⌁' },
    ];
    return this.auth.user()?.role === 'admin'
      ? [...items, { path: '/users', label: 'Usuários', icon: '♙' }]
      : items;
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
    return (
      { admin: 'Administrador', manager: 'Gerente', operator: 'Operador' } as Record<string, string>
    )[this.auth.user()?.role ?? 'operator'];
  }
}
