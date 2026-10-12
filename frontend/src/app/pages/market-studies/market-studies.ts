import { CurrencyPipe, DatePipe, PercentPipe, registerLocaleData } from '@angular/common';
import localePtBr from '@angular/common/locales/pt';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { MarketStudy, MarketStudyConnector } from '../../core/models';
import { PageHeader } from '../../shared/page-header';
import { MoneyInputDirective } from '../../shared/money-input.directive';

registerLocaleData(localePtBr);

@Component({
  selector: 'app-market-studies',
  imports: [
    CurrencyPipe,
    DatePipe,
    FormsModule,
    MoneyInputDirective,
    PageHeader,
    PercentPipe,
    RouterLink,
  ],
  templateUrl: './market-studies.html',
  styleUrl: './market-studies.scss',
})
export class MarketStudiesPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly auth = inject(AuthService);
  readonly form = {
    search_term: '',
    sku: '',
    category_id: '',
    landed_cost: 0,
    target_margin_pct: 25,
    marketplace_fee_pct: 16,
    shipping_cost: 0,
  };
  readonly connector = {
    provider: 'openai_responses' as MarketStudyConnector['provider'],
    model: 'gpt-6-luna',
    base_url: '',
    api_key: '',
    enabled: false,
    has_api_key: false,
  };
  readonly studies = signal<MarketStudy[]>([]);
  readonly selected = signal<MarketStudy | null>(null);
  readonly draftStudy = signal<MarketStudy | null>(null);
  readonly purchaseDraft = { sku: '', quantity: 1 };
  readonly connectorOpen = signal(false);
  readonly loading = signal(false);
  readonly savingConnector = signal(false);
  readonly creatingPurchase = signal(false);
  readonly aiConfigured = signal(false);
  readonly error = signal('');
  readonly connectorMessage = signal('');
  readonly connectorError = signal(false);
  readonly notice = signal('');

  ngOnInit() {
    this.loadStudies();
    this.api.marketStudyConnector().subscribe({
      next: (config) => {
        this.connector.provider = config.provider;
        this.connector.model = config.model;
        this.connector.base_url = config.base_url ?? '';
        this.connector.enabled = config.enabled;
        this.connector.has_api_key = config.has_api_key;
        this.aiConfigured.set(config.configured && config.enabled);
      },
    });
  }
  get canManage() {
    return ['admin', 'manager'].includes(this.auth.user()?.role ?? '');
  }
  loadStudies() {
    this.api.marketStudies().subscribe({
      next: (rows) => {
        this.studies.set(rows);
        if (!this.selected() && rows.length) this.selected.set(rows[0]);
      },
    });
  }
  runStudy() {
    this.loading.set(true);
    this.error.set('');
    this.selected.set(null);
    this.api
      .createMarketStudy({
        search_term: this.form.search_term.trim(),
        sku: this.form.sku.trim() || undefined,
        category_id: this.form.category_id.trim() || undefined,
        landed_cost: Number(this.form.landed_cost),
        target_margin_pct: Number(this.form.target_margin_pct),
        marketplace_fee_pct: Number(this.form.marketplace_fee_pct),
        shipping_cost: Number(this.form.shipping_cost),
      })
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (study) => {
          this.studies.update((current) => [study, ...current]);
          this.selected.set(study);
          this.form.search_term = '';
          window.scrollTo({ top: 0, behavior: 'smooth' });
        },
        error: (e: { error?: { detail?: string } }) =>
          this.error.set(
            e.error?.detail ??
              'Não foi possível gerar o estudo. Confira a integração do Mercado Livre e tente novamente.',
          ),
      });
  }
  saveConnector() {
    this.savingConnector.set(true);
    this.connectorMessage.set('');
    this.api
      .saveMarketStudyConnector({
        provider: this.connector.provider,
        model: this.connector.model.trim(),
        base_url: this.connector.base_url.trim() || undefined,
        api_key: this.connector.api_key.trim() || undefined,
        enabled: this.connector.enabled,
      })
      .pipe(finalize(() => this.savingConnector.set(false)))
      .subscribe({
        next: (saved) => {
          this.connector.api_key = '';
          this.connector.has_api_key = saved.has_api_key;
          this.aiConfigured.set(saved.configured && saved.enabled);
          this.connectorMessage.set('Conector salvo. A chave não será exibida novamente.');
          this.connectorError.set(false);
        },
        error: (e: { error?: { detail?: string } }) => {
          this.connectorMessage.set(e.error?.detail ?? 'Não foi possível salvar o conector.');
          this.connectorError.set(true);
        },
      });
  }
  confidenceLabel(value?: string) {
    return (
      ({ low: 'baixa', medium: 'média', high: 'alta' } as Record<string, string>)[value ?? 'low'] ??
      'baixa'
    );
  }
  createPurchase(study: MarketStudy) {
    this.creatingPurchase.set(true);
    this.api
      .createPurchaseFromMarketStudy(
        study.id,
        this.purchaseDraft.sku.trim(),
        Number(this.purchaseDraft.quantity),
      )
      .pipe(finalize(() => this.creatingPurchase.set(false)))
      .subscribe({
        next: (purchase) => {
          this.studies.update((rows) =>
            rows.map((row) =>
              row.id === study.id ? { ...row, linked_purchase_id: purchase.id } : row,
            ),
          );
          this.selected.update((row) =>
            row?.id === study.id ? { ...row, linked_purchase_id: purchase.id } : row,
          );
          this.draftStudy.set(null);
          this.notice.set(
            'Negociação de compra criada. Você pode adicionar fornecedores e cotações em Compras.',
          );
        },
        error: (e: { error?: { detail?: string } }) =>
          this.notice.set(e.error?.detail ?? 'Não foi possível criar a negociação de compra.'),
      });
  }
}
