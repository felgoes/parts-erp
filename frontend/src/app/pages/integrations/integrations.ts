import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AssistantApi } from '../../core/api/assistant-api';
import { ApiService } from '../../core/api.service';
import {
  MarketplaceConfig,
  MarketplaceStatus,
  ShopeeConfig,
  ShopeeStatus,
} from '../../core/models';
import { AssistantConfiguration } from '../../core/models/assistant';
import { PageHeader } from '../../shared/page-header';

type Rules = { import_orders: boolean; automatic_stock: boolean; sync_documents: boolean };
type MlForm = Rules & {
  client_id: string;
  client_secret: string;
  redirect_uri: string;
  site_id: string;
};
type ShopeeForm = Rules & {
  partner_id: string;
  partner_key: string;
  shop_id: string;
  redirect_uri: string;
  region: string;
};

@Component({
  selector: 'app-integrations',
  imports: [DatePipe, FormsModule, PageHeader],
  templateUrl: './integrations.html',
  styleUrl: './integrations.scss',
})
export class IntegrationsPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly assistantApi = inject(AssistantApi);
  readonly mlStatus = signal<MarketplaceStatus | null>(null);
  readonly mlConfig = signal<MarketplaceConfig | null>(null);
  readonly mlSaving = signal(false);
  readonly mlConnecting = signal(false);
  readonly mlSyncing = signal(false);
  readonly mlMessage = signal('');
  readonly shopeeStatus = signal<ShopeeStatus | null>(null);
  readonly shopeeConfig = signal<ShopeeConfig | null>(null);
  readonly shopeeSaving = signal(false);
  readonly shopeeConnecting = signal(false);
  readonly shopeeMessage = signal('');
  readonly assistantConfig = signal<AssistantConfiguration | null>(null);
  readonly assistantSaving = signal(false);
  readonly assistantTesting = signal(false);
  readonly assistantMessage = signal('');
  assistantModels() {
    const config = this.assistantConfig();
    return config?.providers.find((item) => item.id === this.assistantForm.provider)?.models ?? [];
  }
  assistantSelected() {
    return this.assistantConfig()?.providers.find(
      (item) => item.id === this.assistantForm.provider,
    );
  }
  budgetPercent(): number {
    const value = this.assistantConfig()?.budget.percent_used;
    return value ? Math.min(100, Number(value)) : 0;
  }
  usd(value: string | null | undefined): string {
    return Number(value || 0).toLocaleString('pt-BR', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  mlForm: MlForm = {
    client_id: '',
    client_secret: '',
    redirect_uri: '',
    site_id: 'MLB',
    import_orders: true,
    automatic_stock: true,
    sync_documents: true,
  };
  shopeeForm: ShopeeForm = {
    partner_id: '',
    partner_key: '',
    shop_id: '',
    redirect_uri: '',
    region: 'BR',
    import_orders: true,
    automatic_stock: true,
    sync_documents: true,
  };
  assistantForm = {
    provider: '',
    model: '',
    api_key: '',
    monthly_budget_usd: null as number | null,
  };

  ngOnInit() {
    const connectedReturn = new URLSearchParams(window.location.search).get('connected') === 'true';
    this.api.marketplaceStatus().subscribe((v) => {
      this.mlStatus.set(v);
      if (connectedReturn && v.connected) {
        window.history.replaceState({}, '', window.location.pathname);
        if (
          window.confirm(
            'Conta do Mercado Livre conectada. Deseja sincronizar produtos, pedidos e documentos agora?',
          )
        ) {
          this.syncMercadoLivre();
        }
      }
    });
    this.api.marketplaceConfig().subscribe((v) => {
      this.mlConfig.set(v);
      this.mlForm = { ...this.mlForm, ...v, client_secret: '' };
    });
    this.api.shopeeStatus().subscribe((v) => this.shopeeStatus.set(v));
    this.api.shopeeConfig().subscribe((v) => {
      this.shopeeConfig.set(v);
      this.shopeeForm = { ...this.shopeeForm, ...v, partner_key: '', shop_id: v.shop_id || '' };
    });
    this.loadAssistant();
  }

  loadAssistant() {
    this.assistantApi.configuration().subscribe({
      next: (config) => {
        this.assistantConfig.set(config);
        const provider = config.provider || config.providers[0]?.id || '';
        const models = config.providers.find((item) => item.id === provider)?.models ?? [];
        this.assistantForm = {
          provider,
          model: config.model || models[0]?.id || '',
          api_key: '',
          monthly_budget_usd: config.budget.monthly_limit_usd
            ? Number(config.budget.monthly_limit_usd)
            : null,
        };
      },
      error: (err) => {
        this.assistantMessage.set(
          err?.error?.detail || 'Não foi possível carregar a configuração do assistente.',
        );
      },
    });
  }

  changeAssistantProvider() {
    this.assistantForm = {
      ...this.assistantForm,
      model: this.assistantModels()[0]?.id || '',
    };
  }

  saveAssistant(removeKey = false) {
    const config = this.assistantConfig();
    const sameProvider = config?.provider === this.assistantForm.provider;
    const keyAction = removeKey
      ? 'remove'
      : this.assistantForm.api_key.trim()
        ? 'replace'
        : sameProvider
          ? 'keep'
          : 'remove';
    this.assistantSaving.set(true);
    this.assistantMessage.set('');
    this.assistantApi
      .saveConfiguration({
        provider: this.assistantForm.provider,
        model: this.assistantForm.model,
        key_action: keyAction,
        api_key:
          keyAction === 'replace' ? this.assistantForm.api_key.trim() : undefined,
        monthly_budget_usd: this.assistantForm.monthly_budget_usd,
      })
      .subscribe({
        next: (value) => {
          this.assistantConfig.set(value);
          this.assistantForm = { ...this.assistantForm, api_key: '' };
          this.assistantSaving.set(false);
          this.assistantMessage.set(
            removeKey
              ? 'Chave removida. O assistente fica sem credencial até você salvar outra.'
              : 'Configuração do assistente salva.',
          );
        },
        error: (err) => {
          this.assistantSaving.set(false);
          this.assistantMessage.set(
            err?.error?.detail || 'Não foi possível salvar a configuração do assistente.',
          );
        },
      });
  }

  testAssistant() {
    this.assistantTesting.set(true);
    this.assistantMessage.set('');
    this.assistantApi
      .testConnection({
        provider: this.assistantForm.provider,
        model: this.assistantForm.model,
        api_key: this.assistantForm.api_key.trim() || undefined,
      })
      .subscribe({
        next: () => {
          this.assistantTesting.set(false);
          this.assistantMessage.set('Conexão com o provedor respondeu corretamente.');
        },
        error: (err) => {
          this.assistantTesting.set(false);
          this.assistantMessage.set(
            err?.error?.detail || 'O provedor não respondeu ao teste.',
          );
        },
      });
  }

  saveMercadoLivre() {
    this.mlSaving.set(true);
    this.mlMessage.set('');
    this.api
      .saveMarketplaceConfig({
        ...this.mlForm,
        client_secret: this.mlForm.client_secret || undefined,
      })
      .subscribe({
        next: (v) => {
          this.mlConfig.set(v);
          this.mlForm = { ...this.mlForm, ...v, client_secret: '' };
          this.mlStatus.update((s) => (s ? { ...s, configured: true } : s));
          this.mlMessage.set('Configuração do Mercado Livre salva.');
          this.mlSaving.set(false);
        },
        error: () => {
          this.mlMessage.set('Não foi possível salvar o Mercado Livre.');
          this.mlSaving.set(false);
        },
      });
  }

  connectMercadoLivre() {
    this.mlConnecting.set(true);
    this.api.connectMarketplace().subscribe({
      next: (v) => location.assign(v.authorization_url),
      error: () => this.mlConnecting.set(false),
    });
  }

  syncMercadoLivre() {
    this.mlSyncing.set(true);
    this.mlMessage.set('');
    this.api.syncMarketplace().subscribe({
      next: (v) => {
        this.mlMessage.set(v.message);
        this.mlSyncing.set(false);
      },
      error: (err) => {
        this.mlMessage.set(err?.error?.detail || 'Não foi possível iniciar a sincronização.');
        this.mlSyncing.set(false);
      },
    });
  }

  saveShopee() {
    this.shopeeSaving.set(true);
    this.shopeeMessage.set('');
    this.api
      .saveShopeeConfig({
        ...this.shopeeForm,
        partner_key: this.shopeeForm.partner_key || undefined,
        shop_id: this.shopeeForm.shop_id || undefined,
      })
      .subscribe({
        next: (v) => {
          this.shopeeConfig.set(v);
          this.shopeeForm = { ...this.shopeeForm, ...v, partner_key: '', shop_id: v.shop_id || '' };
          this.shopeeStatus.update((s) => (s ? { ...s, configured: true } : s));
          this.shopeeMessage.set('Configuração da Shopee salva.');
          this.shopeeSaving.set(false);
        },
        error: () => {
          this.shopeeMessage.set('Não foi possível salvar a Shopee.');
          this.shopeeSaving.set(false);
        },
      });
  }

  connectShopee() {
    this.shopeeConnecting.set(true);
    this.api.connectShopee().subscribe({
      next: (v) => location.assign(v.authorization_url),
      error: () => this.shopeeConnecting.set(false),
    });
  }
}
