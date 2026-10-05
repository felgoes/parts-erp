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

registerLocaleData(localePtBr);

@Component({
  selector: 'app-market-studies',
  imports: [CurrencyPipe, DatePipe, FormsModule, PageHeader, PercentPipe, RouterLink],
  template: `
    <app-page-header eyebrow="Inteligência comercial" title="Estudos de mercado" subtitle="Cruze sinais do Mercado Livre com suas vendas, custos e estoque antes de decidir o que comprar ou anunciar." />

    <section class="research-intro" aria-label="Como funciona">
      <div><span class="research-icon">⌕</span><p><strong>Dados observáveis, decisão assistida</strong><br>Veja preços e anúncios comparáveis, tendências disponíveis e giro real do seu ERP. A IA interpreta os sinais — não inventa fornecedor nem promete venda.</p></div>
      @if (canManage) { <button class="secondary" type="button" (click)="connectorOpen.set(!connectorOpen())">{{ connectorOpen() ? 'Fechar configuração de IA' : aiConfigured() ? 'Conector de IA configurado' : 'Configurar conector de IA' }}</button> }
    </section>

    @if (canManage && connectorOpen()) {
      <section class="connector-panel card">
        <div class="panel-heading"><div><p class="eyebrow">Conector plugável</p><h2>Análise assistida por IA</h2><p>Opcional. Sem chave configurada, os indicadores e cálculos continuam funcionando sem IA.</p></div><span class="connector-state" [class.is-on]="aiConfigured()">{{ aiConfigured() ? 'Conectado' : 'Não configurado' }}</span></div>
        <div class="connector-grid">
          <label>Provedor<select [(ngModel)]="connector.provider"><option value="openai_responses">OpenAI (Responses API)</option><option value="openai_compatible">Compatível com OpenAI (endpoint próprio)</option></select></label>
          <label>Modelo<input [(ngModel)]="connector.model" placeholder="Ex.: gpt-6-luna" /></label>
          @if (connector.provider === 'openai_compatible') { <label class="connector-url">URL base HTTPS<input [(ngModel)]="connector.base_url" placeholder="https://api.seuprovedor.com/v1" /></label> }
          <label class="connector-key">Chave de API<input type="password" [(ngModel)]="connector.api_key" autocomplete="new-password" [placeholder]="connector.has_api_key ? 'Chave salva — informe outra somente para substituir' : 'Cole aqui a chave do provedor'" /></label>
          <label class="connector-enable"><input type="checkbox" [(ngModel)]="connector.enabled" /> Usar IA nos novos estudos</label>
          <button class="primary" type="button" [disabled]="savingConnector()" (click)="saveConnector()">{{ savingConnector() ? 'Salvando…' : 'Salvar conector' }}</button>
        </div>
        <p class="connector-privacy">A chave fica criptografada no banco e nunca volta pela API. Quando habilitada, somente a busca e dados agregados do estudo (incluindo custo informado) são enviados ao provedor escolhido; nenhum dado de cliente ou pedido é enviado. O provedor pode cobrar pelo uso da API. A integração começa desligada.</p>
        @if (connectorMessage()) { <p class="inline-message" [class.is-error]="connectorError()">{{ connectorMessage() }}</p> }
      </section>
    }

    <div class="research-layout">
      @if (canManage) { <section class="study-form card">
        <div class="panel-heading"><div><p class="eyebrow">Novo estudo</p><h2>Pesquise uma oportunidade</h2><p>Use nome da peça, código OEM ou aplicação. Informe custo posto na sua loja para comparar a margem.</p></div><span class="step-mark">01</span></div>
        <div class="study-fields">
          <label class="field-wide">Peça ou termo de busca<input [(ngModel)]="form.search_term" maxlength="200" placeholder="Ex.: bomba d’água Tiggo 7 1.5T" /></label>
          <label>SKU interno (opcional)<input [(ngModel)]="form.sku" maxlength="80" placeholder="Usa vendas e saldo existentes" /></label>
          <label>Categoria ML (opcional)<input [(ngModel)]="form.category_id" maxlength="40" placeholder="Ex.: MLB..." /></label>
          <label>Custo unitário da peça (R$)<input type="number" min="0" step="0.01" [(ngModel)]="form.landed_cost" /></label>
          <label>Frete unitário rateado (R$)<input type="number" min="0" step="0.01" [(ngModel)]="form.shipping_cost" /></label>
          <label>Taxas estimadas do canal (%)<input type="number" min="0" max="79" step="0.1" [(ngModel)]="form.marketplace_fee_pct" /></label>
          <label>Margem desejada (%)<input type="number" min="0" max="79" step="0.1" [(ngModel)]="form.target_margin_pct" /></label>
        </div>
        <div class="study-submit"><small>Pesquisa até 50 anúncios do ML, tendências e histórico ERP de 90 dias para o SKU.</small><button class="primary" type="button" [disabled]="loading() || !form.search_term.trim()" (click)="runStudy()">{{ loading() ? 'Analisando mercado…' : 'Gerar estudo' }} <span aria-hidden="true">→</span></button></div>
        @if (error()) { <p class="inline-message is-error" role="alert">{{ error() }}</p> }
      </section> } @else { <section class="study-form card read-only-note"><p class="eyebrow">Acesso de consulta</p><h2>Peça um novo estudo à gestão</h2><p>Você pode consultar análises já salvas. Para consumir a API do marketplace e executar uma nova pesquisa, é necessário perfil de gerente ou administrador.</p></section> }

      <aside class="method-card">
        <p class="eyebrow">Como ler o resultado</p><h2>Uma referência para decidir melhor</h2>
        <div><span>1</span><p><strong>Concorrência</strong><small>Mediana e faixa de preço dos anúncios semelhantes.</small></p></div>
        <div><span>2</span><p><strong>Seu cenário</strong><small>Preço de equilíbrio e preço necessário para a margem indicada.</small></p></div>
        <div><span>3</span><p><strong>Próxima ação</strong><small>Converta em rascunho de compra e registre cotações reais.</small></p></div>
        <small class="method-note">Não é cotação comercial, previsão garantida de giro nem validação de aplicação automotiva.</small>
      </aside>
    </div>

    @if (selected(); as study) {
      <section class="study-result card" aria-live="polite">
        <div class="result-heading"><div><p class="eyebrow">Estudo salvo · {{ study.created_at | date:'dd/MM/yyyy HH:mm' }}</p><h2>{{ study.search_term }}</h2><p>{{ study.sku ? 'SKU ' + study.sku + ' · ' : '' }}Dados observados em {{ study.result.observed_at | date:'dd/MM/yyyy HH:mm':'':'pt-BR' }}</p></div><span class="result-badge" [class.is-limited]="study.status === 'insufficient_data'">{{ study.status === 'completed' ? 'Dados comparáveis' : 'Amostra limitada' }}</span></div>
        <div class="market-metrics">
          <article><span>Preço mediano comparável</span><strong>{{ study.result.market_metrics.median_price ? (+study.result.market_metrics.median_price | currency:'BRL':'symbol':'1.2-2':'pt-BR') : 'Sem amostra' }}</strong><small>{{ study.result.market_metrics.comparable_offers }} anúncios semelhantes</small></article>
          <article><span>Faixa observada</span><strong>{{ study.result.market_metrics.min_price ? (+study.result.market_metrics.min_price | currency:'BRL':'symbol':'1.0-0':'pt-BR') + ' — ' + (+study.result.market_metrics.max_price! | currency:'BRL':'symbol':'1.0-0':'pt-BR') : '—' }}</strong><small>Preços anunciados; não incluem todas as condições</small></article>
          <article><span>Preço para margem desejada</span><strong>{{ study.result.price_scenario.target_price ? (+study.result.price_scenario.target_price | currency:'BRL':'symbol':'1.2-2':'pt-BR') : '—' }}</strong><small>Após taxas estimadas de {{ study.marketplace_fee_pct }}%</small></article>
          <article><span>Margem no preço mediano</span><strong [class.negative]="+(study.result.price_scenario.market_margin_at_median_pct ?? 0) < 0">{{ study.result.price_scenario.market_margin_at_median_pct !== null ? study.result.price_scenario.market_margin_at_median_pct + '%' : '—' }}</strong><small>Custo posto informado: {{ (study.landed_cost + study.shipping_cost) | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</small></article>
        </div>
        <div class="signal-grid">
          <article><p class="eyebrow">Sinal de giro no ERP</p><strong>{{ study.sku ? study.result.internal_sales.units_last_90_days : 'SKU não informado' }}{{ study.sku ? ' un. em 90 dias' : '' }}</strong><small>{{ study.sku ? study.result.internal_sales.units_per_month + ' un./mês; média observada, não previsão.' : 'Informe SKU para cruzar com vendas e saldo.' }}</small></article>
          <article><p class="eyebrow">Anúncios encontrados</p><strong>{{ study.result.market_metrics.offers_found }}</strong><small>{{ study.result.market_metrics.sold_units_lifetime_in_comparables }} vendas acumuladas somadas nos anúncios comparáveis — não representam período mensal.</small></article>
          <article><p class="eyebrow">Tendências do ML</p><strong>{{ study.result.market_metrics.trend_keyword_matches }} termos relacionados</strong><small>O recurso de tendências é semanal e não garante demanda futura.</small></article>
        </div>

        @if (study.result.ai_report; as ai) {
          @if (ai.error) { <p class="inline-message is-error">{{ ai.error }}</p> } @else {
            <section class="ai-report"><div class="ai-title"><span>✳</span><div><p class="eyebrow">Leitura assistida por IA · confiança {{ confidenceLabel(ai.confidence) }}</p><h3>O que os sinais sugerem</h3></div></div><p>{{ ai.summary }}</p><div class="ai-columns">@if (ai.opportunities?.length) { <div><strong>Oportunidades a investigar</strong><ul>@for (tip of ai.opportunities; track tip) { <li>{{ tip }}</li> }</ul></div> } @if (ai.risks?.length) { <div><strong>Pontos de atenção</strong><ul>@for (tip of ai.risks; track tip) { <li>{{ tip }}</li> }</ul></div> } @if (ai.next_steps?.length) { <div><strong>Próximos passos</strong><ul>@for (tip of ai.next_steps; track tip) { <li>{{ tip }}</li> }</ul></div> }</div></section>
          }
        } @else { <p class="ai-disabled">Sem IA conectada: resultados acima são cálculos e dados diretos. Configure um provedor para receber uma síntese qualitativa.</p> }

        @if (study.result.trend_matches.length) { <section class="evidence-section"><div class="subheading"><div><p class="eyebrow">Interesse de busca</p><h3>Termos em tendência</h3></div></div><div class="trend-chips">@for (trend of study.result.trend_matches; track trend.keyword) { <a [href]="trend.url" target="_blank" rel="noopener noreferrer">{{ trend.keyword }} ↗</a> }</div></section> }

        <section class="evidence-section"><div class="subheading"><div><p class="eyebrow">Comparação de mercado</p><h3>Anúncios para conferir</h3><p>{{ study.result.possible_sources_note }}</p></div><span>{{ study.result.offers.length }} resultados</span></div>
          @if (study.result.offers.length) { <div class="offers-list">@for (offer of study.result.offers; track offer.id) { <article class="offer-row">@if (offer.thumbnail) { <img [src]="offer.thumbnail" alt="" loading="lazy" /> } @else { <span class="offer-placeholder">◇</span> }<div class="offer-info"><strong>{{ offer.title }}</strong><small>Anúncio {{ offer.id }} · relevância {{ offer.similarity | percent:'1.0-0':'pt-BR' }} · {{ offer.sold_quantity_lifetime ?? '—' }} vendas acumuladas</small></div><strong class="offer-price">{{ +offer.price | currency:'BRL':'symbol':'1.2-2':'pt-BR' }}</strong>@if (offer.permalink) { <a class="offer-link" [href]="offer.permalink" target="_blank" rel="noopener noreferrer" aria-label="Abrir anúncio em nova guia">↗</a> }</article> }</div> } @else { <div class="empty-result"><strong>Não encontrei anúncios comparáveis suficientes.</strong><span>Tente buscar pelo código OEM, nome comercial ou modelo do veículo.</span></div> }
        </section>
        <div class="limitations-note"><strong>Limites dos dados:</strong> disponibilidade pode vir aproximada; venda acumulada do anúncio não é giro mensal; vendedor do anúncio é apenas uma pista para cotação, não fornecedor validado; compatibilidade deve ser conferida.</div>

        <div class="result-actions">
      @if (study.linked_purchase_id) { <a class="primary" routerLink="/purchases">Abrir negociação de compra →</a> }
          @else { <button class="secondary" type="button" (click)="draftStudy.set(study)">Transformar em rascunho de compra</button> }
        </div>
        @if (draftStudy()?.id === study.id) { <div class="draft-box"><p><strong>Iniciar negociação de compra</strong><small>O estudo não faz pedido. Vai abrir uma negociação para você inserir cotações e decidir.</small></p><label>SKU a negociar<input [(ngModel)]="purchaseDraft.sku" placeholder="SKU interno ou provisório" /></label><label>Quantidade desejada<input type="number" min="0.001" step="0.001" [(ngModel)]="purchaseDraft.quantity" /></label><button class="primary" [disabled]="creatingPurchase() || !purchaseDraft.sku.trim()" (click)="createPurchase(study)">{{ creatingPurchase() ? 'Criando…' : 'Criar negociação' }}</button><button class="text-button" (click)="draftStudy.set(null)">Cancelar</button></div> }
      </section>
    }

    <section class="history-section"><div class="history-heading"><div><p class="eyebrow">Biblioteca de análises</p><h2>Estudos recentes</h2><p>Snapshots preservam os preços observados no momento da pesquisa.</p></div><span>{{ studies().length }} estudos</span></div>
      @if (studies().length) { <div class="history-list">@for (study of studies(); track study.id) { <button class="history-row" [class.is-selected]="selected()?.id === study.id" (click)="selected.set(study)"><span class="history-mark">⌕</span><span class="history-main"><strong>{{ study.search_term }}</strong><small>{{ study.sku ? study.sku + ' · ' : '' }}{{ study.created_at | date:'dd/MM/yyyy HH:mm' }}</small></span><span class="history-price">{{ study.result.market_metrics.median_price ? (+study.result.market_metrics.median_price | currency:'BRL':'symbol':'1.2-2':'pt-BR') : 'Sem amostra' }}<small>{{ study.result.market_metrics.comparable_offers }} comparáveis</small></span><span class="history-arrow">→</span></button> }</div> }
      @else if (!loading()) { <div class="empty-history"><span>◌</span><div><strong>Seu primeiro estudo começa por aqui</strong><p>Pesquise uma peça para comparar mercado, custo posto e sinais reais de giro.</p></div></div> }
    </section>
    @if (notice()) { <p class="toast" role="status">{{ notice() }}</p> }
  `,
  styleUrl: './market-studies.scss',
})
export class MarketStudiesPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly auth = inject(AuthService);
  readonly form = { search_term: '', sku: '', category_id: '', landed_cost: 0, target_margin_pct: 25, marketplace_fee_pct: 16, shipping_cost: 0 };
  readonly connector = { provider: 'openai_responses' as MarketStudyConnector['provider'], model: 'gpt-6-luna', base_url: '', api_key: '', enabled: false, has_api_key: false };
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
    this.api.marketStudyConnector().subscribe({ next: (config) => {
      this.connector.provider = config.provider;
      this.connector.model = config.model;
      this.connector.base_url = config.base_url ?? '';
      this.connector.enabled = config.enabled;
      this.connector.has_api_key = config.has_api_key;
      this.aiConfigured.set(config.configured && config.enabled);
    } });
  }
  get canManage() { return ['admin', 'manager'].includes(this.auth.user()?.role ?? ''); }
  loadStudies() {
    this.api.marketStudies().subscribe({ next: (rows) => {
      this.studies.set(rows);
      if (!this.selected() && rows.length) this.selected.set(rows[0]);
    } });
  }
  runStudy() {
    this.loading.set(true); this.error.set(''); this.selected.set(null);
    this.api.createMarketStudy({
      search_term: this.form.search_term.trim(), sku: this.form.sku.trim() || undefined,
      category_id: this.form.category_id.trim() || undefined, landed_cost: Number(this.form.landed_cost),
      target_margin_pct: Number(this.form.target_margin_pct), marketplace_fee_pct: Number(this.form.marketplace_fee_pct),
      shipping_cost: Number(this.form.shipping_cost),
    }).pipe(finalize(() => this.loading.set(false))).subscribe({
      next: (study) => { this.studies.update((current) => [study, ...current]); this.selected.set(study); this.form.search_term = ''; window.scrollTo({ top: 0, behavior: 'smooth' }); },
      error: (e: { error?: { detail?: string } }) => this.error.set(e.error?.detail ?? 'Não foi possível gerar o estudo. Confira a integração do Mercado Livre e tente novamente.'),
    });
  }
  saveConnector() {
    this.savingConnector.set(true); this.connectorMessage.set('');
    this.api.saveMarketStudyConnector({ provider: this.connector.provider, model: this.connector.model.trim(), base_url: this.connector.base_url.trim() || undefined, api_key: this.connector.api_key.trim() || undefined, enabled: this.connector.enabled }).pipe(finalize(() => this.savingConnector.set(false))).subscribe({
      next: (saved) => { this.connector.api_key = ''; this.connector.has_api_key = saved.has_api_key; this.aiConfigured.set(saved.configured && saved.enabled); this.connectorMessage.set('Conector salvo. A chave não será exibida novamente.'); this.connectorError.set(false); },
      error: (e: { error?: { detail?: string } }) => { this.connectorMessage.set(e.error?.detail ?? 'Não foi possível salvar o conector.'); this.connectorError.set(true); },
    });
  }
  confidenceLabel(value?: string) { return ({ low: 'baixa', medium: 'média', high: 'alta' } as Record<string, string>)[value ?? 'low'] ?? 'baixa'; }
  createPurchase(study: MarketStudy) {
    this.creatingPurchase.set(true);
    this.api.createPurchaseFromMarketStudy(study.id, this.purchaseDraft.sku.trim(), Number(this.purchaseDraft.quantity)).pipe(finalize(() => this.creatingPurchase.set(false))).subscribe({
      next: (purchase) => { this.studies.update((rows) => rows.map((row) => row.id === study.id ? { ...row, linked_purchase_id: purchase.id } : row)); this.selected.update((row) => row?.id === study.id ? { ...row, linked_purchase_id: purchase.id } : row); this.draftStudy.set(null); this.notice.set('Negociação de compra criada. Você pode adicionar fornecedores e cotações em Compras.'); },
      error: (e: { error?: { detail?: string } }) => this.notice.set(e.error?.detail ?? 'Não foi possível criar a negociação de compra.'),
    });
  }
}
