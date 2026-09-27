import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { MarketplaceStatus } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-integrations',
  imports: [DatePipe, PageHeader],
  template: `
    <app-page-header
      eyebrow="Configuração"
      title="Integrações"
      subtitle="Conecte seus canais sem expor credenciais."
    ></app-page-header>
    <section class="integration-grid">
      <article class="integration-card">
        <div class="integration-logo ml">ML</div>
        <div class="integration-title">
          <div>
            <h2>Mercado Livre</h2>
            <p>Pedidos, estoque e documentos fiscais</p>
          </div>
          @if (status()?.connected) {
            <span class="badge success">Conectado</span>
          } @else {
            <span class="badge">Desconectado</span>
          }
        </div>
        @if (status(); as s) {
          <div class="features">
            <div>
              <span>✓</span>
              <p>
                <strong>Importação de pedidos</strong
                ><small>Notificações processadas em segundo plano</small>
              </p>
            </div>
            <div>
              <span>✓</span>
              <p>
                <strong>Baixa segura de estoque</strong
                ><small>Conciliação pelo SKU e proteção contra duplicidade</small>
              </p>
            </div>
            <div>
              <span>✓</span>
              <p>
                <strong>XML e DANFE</strong><small>Download depois da autorização da NF-e</small>
              </p>
            </div>
          </div>
          @if (s.connected) {
            <div class="account">
              <span class="avatar">{{ (s.nickname || 'M')[0] }}</span>
              <div>
                <strong>{{ s.nickname }}</strong
                ><small
                  >Seller ID {{ s.seller_id }} · token até
                  {{ s.token_expires_at | date: 'dd/MM/yyyy HH:mm' }}</small
                >
              </div>
            </div>
          } @else if (!s.configured) {
            <div class="config-warning">
              <strong>Credenciais pendentes</strong>
              <p>
                Preencha as variáveis <code>MERCADOLIVRE_CLIENT_ID</code> e
                <code>MERCADOLIVRE_CLIENT_SECRET</code> no ambiente do servidor.
              </p>
            </div>
          }
          <button
            class="primary full"
            [disabled]="!s.configured || connecting()"
            (click)="connect()"
          >
            {{ s.connected ? 'Reconectar conta' : 'Conectar Mercado Livre' }}
          </button>
        }
      </article>
      <aside class="security-card">
        <span>⌾</span>
        <h2>Segurança por padrão</h2>
        <p>
          Tokens OAuth ficam criptografados no banco. Segredos da aplicação existem apenas nas
          variáveis do ambiente e nunca entram no Git.
        </p>
        <ul>
          <li>OAuth com estado assinado e expiração</li>
          <li>Refresh token automático</li>
          <li>Webhook sem credenciais na URL</li>
          <li>Processamento idempotente</li>
        </ul>
      </aside>
    </section>
  `,
  styleUrl: './integrations.scss',
})
export class IntegrationsPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly status = signal<MarketplaceStatus | null>(null);
  readonly connecting = signal(false);
  ngOnInit() {
    this.api.marketplaceStatus().subscribe((v) => this.status.set(v));
  }
  connect() {
    this.connecting.set(true);
    this.api
      .connectMarketplace()
      .subscribe({
        next: (v) => location.assign(v.authorization_url),
        error: () => this.connecting.set(false),
      });
  }
}
