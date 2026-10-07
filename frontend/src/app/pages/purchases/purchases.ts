import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { Product, Purchase, PurchaseItem, PurchaseStatus } from '../../core/models';
import { canAdjustStock, canManagePurchases, canReadCosts } from '../../core/user-access';
import { DateRange, quickDateRange } from '../../core/quick-date-ranges';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';

@Component({
  selector: 'app-purchases',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, ReactiveFormsModule, PageHeader, PeriodFilter],
  template: `
    <app-page-header eyebrow="Suprimentos" title="Compras" subtitle="Peças para o estoque e despesas operacionais da empresa.">
      @if (canManagePurchases()) { <button class="primary" type="button" (click)="openNew()">+ Nova compra</button> }
    </app-page-header>
    <section class="purchase-summary">
      @for (card of summary(); track card.status) {
        <button type="button" class="purchase-stat" [class.active-stat]="statusFilter() === card.status" (click)="toggleStatus(card.status)">
          <span>{{ card.label }}</span><strong>{{ card.count }}</strong><small>{{ card.note }}</small>
        </button>
      }
    </section>
    <app-period-filter heading="Período das compras" description="Filtra pela data de abertura da negociação." ariaLabel="Filtrar compras por período" initialPreset="last30" [initialStartDate]="startDate()" [initialEndDate]="endDate()" (rangeChange)="applyPeriod($event)" />
    <section class="purchase-toolbar">
      <label class="purchase-search"><span>⌕</span><input aria-label="Buscar compras" placeholder="Buscar número, peça ou fornecedor…" [value]="search()" (input)="search.set($any($event.target).value)" /></label>
      <label class="purchase-select">Etapa <select [value]="statusFilter()" (change)="statusFilter.set($any($event.target).value)"><option value="all">Todas</option>@for (status of statuses; track status.value) { <option [value]="status.value">{{ status.label }}</option> }</select></label>
      <span class="muted">{{ filtered().length }} compras</span>
    </section>
    <section class="card purchase-table-card" [class.restricted-costs]="!canReadCosts()">
      <div class="table-wrap"><table><thead><tr><th>COMPRA</th><th>PEÇAS</th><th>FORNECEDOR / COTAÇÕES</th><th>ETAPA</th><th>PREVISÃO</th><th>ABERTA EM</th><th></th></tr></thead><tbody>
        @for (purchase of filtered(); track purchase.id) {
          <tr class="purchase-row" tabindex="0" (click)="openDetails(purchase)" (keydown.enter)="openDetails(purchase)">
            <td><strong>{{ purchase.number }}</strong><small>{{ purchase.purchase_type === 'expense' ? 'Despesa da empresa' : (purchase.items.length + (purchase.items.length === 1 ? ' item' : ' itens')) }}</small></td>
            <td><div class="purchase-products">@if (purchase.purchase_type === 'expense') { <span>{{ purchase.expense_category }}</span><small>{{ purchase.expense_amount | currency:'BRL' }}</small> } @else { @for (item of purchase.items.slice(0, 2); track item.id) { <span>{{ item.description }}</span> } @if (purchase.items.length > 2) { <small>+{{ purchase.items.length - 2 }} outras</small> } }</div></td>
            <td>@if (purchase.purchase_type === 'expense') { <strong>{{ purchase.supplier_name || 'Sem fornecedor' }}</strong><small>Despesa lançada</small> } @else if (selectedQuote(purchase); as quote) { <strong>{{ quote.supplier_name }}</strong><small>{{ quote.total | currency:'BRL' }} · cotação escolhida</small> } @else { <strong class="muted">Em cotação</strong><small>{{ purchase.quotes.length }} {{ purchase.quotes.length === 1 ? 'proposta registrada' : 'propostas registradas' }}</small> }</td>
            <td><span class="purchase-badge" [attr.data-status]="purchase.status">{{ purchase.purchase_type === 'expense' ? 'Lançada' : statusLabel(purchase.status) }}</span></td>
            <td>{{ purchase.needed_by ? (purchase.needed_by | date:'dd/MM/yyyy') : '—' }}</td><td>{{ purchase.created_at | date:'dd/MM/yyyy' }}</td><td class="row-action">Abrir <span>→</span></td>
          </tr>
        } @empty { <tr><td colspan="7"><div class="purchase-empty"><strong>Nenhuma compra neste período</strong><span>Comece uma negociação para acompanhar propostas e recebimentos por aqui.</span>@if (canManagePurchases()) { <button class="secondary" (click)="openNew()">Criar compra</button> }</div></td></tr> }
      </tbody></table></div>
    </section>

    @if (showNew()) {
      <div class="modal-backdrop" (click)="showNew.set(false)"><section class="modal wide purchase-modal" role="dialog" aria-modal="true" aria-labelledby="new-purchase-title" (click)="$event.stopPropagation()">
        <div class="modal-head"><div><p class="eyebrow">Suprimentos</p><h2 id="new-purchase-title">Nova compra</h2><p class="modal-intro">Cadastre peças para o estoque ou uma despesa da empresa com seus documentos.</p></div><button class="close" aria-label="Fechar" (click)="showNew.set(false)">×</button></div>
        <form [formGroup]="form" (ngSubmit)="create()">
          <div class="purchase-form-meta"><label>Tipo de lançamento<select formControlName="purchase_type"><option value="parts">Peças para estoque</option><option value="expense">Despesa da empresa</option></select></label><label>Fornecedor / favorecido<input formControlName="supplier_name" placeholder="Nome da empresa ou pessoa" /></label><label>Previsão desejada<input type="date" formControlName="needed_by" /></label><label class="notes-field">Observações<textarea rows="2" formControlName="notes" placeholder="Detalhes do lançamento"></textarea></label></div>
          @if (form.controls.purchase_type.value === 'expense') { <div class="purchase-form-section expense-fields"><div class="section-heading"><div><p class="eyebrow">Despesa operacional</p><h3>Dados do gasto</h3></div></div><div class="purchase-form-meta"><label>Categoria<select formControlName="expense_category"><option value="">Selecione…</option>@for (category of expenseCategories; track category) { <option [value]="category">{{ category }}</option> }</select></label><label>Valor total<input type="number" min="0" step="0.01" formControlName="expense_amount" /></label></div></div> } @else { <div class="purchase-form-section"><div class="section-heading"><div><p class="eyebrow">Lista de compra</p><h3>Peças em negociação</h3></div><button type="button" class="secondary small" (click)="addLine()">+ Adicionar peça</button></div>
            <p class="purchase-flow-hint">Nesta etapa, informe somente as peças e quantidades. Preços, frete, impostos e descontos entram em cada cotação de fornecedor.</p><div formArrayName="items" class="purchase-line-list">@for (line of lines.controls; track $index; let i = $index) { <div class="purchase-line-form" [formGroupName]="i"><label>Produto cadastrado<select formControlName="product_id" (change)="selectProduct(i, $any($event.target).value)"><option value="">Cadastrar/vincular depois</option>@for (product of products(); track product.id) { <option [value]="product.id">{{ product.sku }} · {{ product.name }}</option> }</select></label><label>SKU<input formControlName="sku" placeholder="Ex.: LR174890" /></label><label class="line-description">Peça / descrição<input formControlName="description" placeholder="Nome da peça" /></label><label>Quantidade<input type="number" min="0.001" step="0.001" formControlName="quantity" /></label>@if (lines.length > 1) { <button type="button" class="remove-line" aria-label="Remover peça" (click)="removeLine(i)">×</button> }</div> }</div>
          </div> }
          <label class="attachment-picker">Documentos <input type="file" multiple accept=".pdf,.xml,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx" (change)="setAttachments($any($event.target).files)" /><small>{{ selectedFiles().length ? selectedFiles().length + ' arquivo(s) selecionado(s)' : 'Nota fiscal, recibo, boleto ou comprovante (até 10 arquivos)' }}</small></label>
          @if (error()) { <p class="purchase-error" role="alert">{{ error() }}</p> }
          <div class="purchase-form-actions"><span class="muted">{{ form.controls.purchase_type.value === 'expense' ? 'Despesa lançada sem movimentar estoque' : lines.length + (lines.length === 1 ? ' peça' : ' peças') + ' · estoque só muda no recebimento' }}</span><button class="primary" [disabled]="saving() || (form.controls.purchase_type.value === 'parts' && form.invalid) || (form.controls.purchase_type.value === 'expense' && (!form.controls.expense_category.value || form.controls.expense_amount.value === null))">{{ saving() ? 'Salvando…' : 'Salvar compra' }}</button></div>
        </form>
      </section></div>
    }

    @if (detail(); as purchase) {
      <div class="modal-backdrop" (click)="detail.set(null)"><section class="modal wide purchase-modal purchase-detail" [class.restricted-costs]="!canReadCosts()" [class.read-only-purchases]="!canManagePurchases()" [class.no-receiving]="!canAdjustStock()" [class.costs-pending]="purchase.purchase_type === 'parts' && !purchase.selected_quote_id" role="dialog" aria-modal="true" [attr.aria-label]="'Compra ' + purchase.number" (click)="$event.stopPropagation()">
        <div class="modal-head"><div><p class="eyebrow">Suprimentos · {{ purchase.number }}</p><h2>{{ purchase.number }}</h2><p class="modal-intro">Criada em {{ purchase.created_at | date:'dd/MM/yyyy HH:mm' }} @if (purchase.needed_by) { · Previsão {{ purchase.needed_by | date:'dd/MM/yyyy' }} }</p></div><div class="detail-head-actions"><span class="purchase-badge" [attr.data-status]="purchase.status">{{ purchase.purchase_type === 'expense' ? 'Lançada' : statusLabel(purchase.status) }}</span><button class="close" aria-label="Fechar" (click)="detail.set(null)">×</button></div></div>
        @if (purchase.purchase_type === 'parts') { <div class="purchase-steps" aria-label="Etapas da compra">@for (step of workflow; track step.value; let i = $index) { <div class="purchase-step" [class.step-done]="stepIndex(purchase.status) > i" [class.step-current]="stepIndex(purchase.status) === i"><span>{{ stepIndex(purchase.status) > i ? '✓' : i + 1 }}</span><small>{{ step.label }}</small></div> }</div> } @else { <div class="expense-banner"><strong>Despesa da empresa</strong><span>{{ purchase.expense_category }} · {{ purchase.expense_amount | currency:'BRL' }}</span></div> }
        <div class="purchase-detail-grid">
          <div class="purchase-detail-main">
            @if (purchase.purchase_type === 'parts') { <section class="purchase-form-section"><div class="section-heading"><div><p class="eyebrow">Itens e recebimento</p><h3>Peças da compra</h3></div></div><div class="purchase-item-cards">@for (item of purchase.items; track item.id) { <article class="purchase-item-card"><div class="item-title"><div><strong>{{ item.description }}</strong><small><code>{{ item.sku }}</code>@if (item.product_id) { · vinculada ao catálogo } @else { · ainda sem produto no catálogo }</small></div><strong>{{ item.unit_cost | currency:'BRL' }} <small>/ un. final</small></strong></div><div class="item-cost-breakdown"><span>Base: {{ item.base_unit_cost | currency:'BRL' }}</span><span>Frete: {{ item.freight_amount | currency:'BRL' }}</span><span>Impostos: {{ item.tax_amount | currency:'BRL' }}</span><span>Desconto: -{{ item.discount_amount | currency:'BRL' }}</span></div>@if (purchase.status !== 'received' && purchase.status !== 'cancelled' && canManagePurchases()) { <div class="item-cost-editor"><label>Preço base<input type="number" min="0" step="0.01" [value]="itemCost(item, 'base_unit_cost')" (input)="setItemCost(item, 'base_unit_cost', $any($event.target).value)" /></label><label>Frete<input type="number" min="0" step="0.01" [value]="itemCost(item, 'freight_amount')" (input)="setItemCost(item, 'freight_amount', $any($event.target).value)" /></label><label>Impostos<input type="number" min="0" step="0.01" [value]="itemCost(item, 'tax_amount')" (input)="setItemCost(item, 'tax_amount', $any($event.target).value)" /></label><label>Desconto<input type="number" min="0" step="0.01" [value]="itemCost(item, 'discount_amount')" (input)="setItemCost(item, 'discount_amount', $any($event.target).value)" /></label><button type="button" class="secondary small" [disabled]="saving()" (click)="saveItemCosts(purchase, item)">Atualizar custo</button></div> }<div class="receipt-progress"><span>Recebido <b>{{ item.received_quantity | number:'1.0-3' }} / {{ item.quantity | number:'1.0-3' }} un.</b></span><div><i [style.width.%]="progress(item)"></i></div></div>@if (purchase.status === 'ordered' || purchase.status === 'partially_received') { <div class="receive-controls"><label>Receber agora<input type="number" min="0.001" [max]="item.quantity - item.received_quantity" step="0.001" [value]="receiveQty(item)" (input)="setReceiveQty(item, $any($event.target).value)" /></label>@if (!item.product_id) { <label class="map-product">Vincular produto existente<select [value]="receiveProduct(item)" (change)="setReceiveProduct(item, $any($event.target).value)"><option value="">Selecione um produto…</option>@for (product of products(); track product.id) { <option [value]="product.id">{{ product.sku }} · {{ product.name }}</option> }</select></label><label class="create-product-check"><input type="checkbox" [checked]="createNewProduct(item)" (change)="setCreateNewProduct(item, $any($event.target).checked)" /> Criar produto no catálogo ao receber</label> }<button type="button" class="secondary small" [disabled]="saving() || receiveQty(item) <= 0" (click)="receive(item)">Registrar recebimento</button></div> }</article> }</div></section> }
            @if (purchase.purchase_type === 'parts' && purchase.status === 'negotiating') { <section class="purchase-form-section"><div class="section-heading"><div><p class="eyebrow">Concorrência</p><h3>Cotações de fornecedores</h3></div></div>@if (purchase.quotes.length) { <div class="quote-cards">@for (quote of purchase.quotes; track quote.id) { <article class="quote-card" [class.quote-selected]="purchase.selected_quote_id === quote.id"><div><strong>{{ quote.supplier_name }}</strong><b>{{ quote.total | currency:'BRL' }}</b></div><p>{{ quote.delivery_days !== null ? quote.delivery_days + ' dias para entrega' : 'Prazo não informado' }} @if (quote.payment_terms) { · {{ quote.payment_terms }} }</p><div class="quote-cost-summary">@for (item of purchase.items; track item.id) { <small>{{ item.sku }} · {{ quote.item_costs?.[item.id] | currency:'BRL' }}/un.</small> }</div>@if (quote.notes) { <small>{{ quote.notes }}</small> }<button type="button" class="secondary small" (click)="selectQuote(quote.id)">Escolher esta cotação</button></article> }</div> } @else { <p class="muted">Registre as propostas recebidas para comparar preço e prazo.</p> }
              <form class="quote-form" [formGroup]="quoteForm" (ngSubmit)="addQuote()"><div class="quote-item-costs"><strong>Custo unitário dos itens</strong>@for (item of purchase.items; track item.id) { <label>{{ item.sku }} · {{ item.description }}<input type="number" min="0" step="0.01" [value]="quoteUnitCost(item)" (input)="setQuoteUnitCost(item, $any($event.target).value)" /></label> }</div><label>Fornecedor<input formControlName="supplier_name" placeholder="Nome do fornecedor" /></label><label>Contato<input formControlName="supplier_contact" placeholder="Telefone ou e-mail" /></label><label>Frete<input type="number" min="0" step="0.01" formControlName="freight_amount" /></label><label>Impostos<input type="number" min="0" step="0.01" formControlName="tax_amount" /></label><label>Desconto<input type="number" min="0" step="0.01" formControlName="discount_amount" /></label><label>Ratear acréscimos/desconto<select formControlName="allocation_method"><option value="proportional">Proporcional ao subtotal de cada item</option><option value="quantity">Por quantidade de peças</option></select></label><label>Total final da proposta<input type="number" [value]="quoteTotal(purchase)" readonly /></label><label>Prazo (dias)<input type="number" min="0" formControlName="delivery_days" /></label><label>Condição de pagamento<input formControlName="payment_terms" placeholder="Ex.: 30/60 dias" /></label><label class="quote-notes">Observações<input formControlName="notes" placeholder="Validade ou detalhes da proposta…" /></label><small class="quote-cost-hint">Custo considerado: {{ quoteTotal(purchase) | currency:'BRL' }} · frete, impostos e desconto serão distribuídos automaticamente.</small><button class="primary" [disabled]="quoteForm.invalid || !quoteCostsComplete(purchase) || quoteTotal(purchase) < 0 || saving()">Registrar cotação</button></form>
            </section> }
            @if (purchase.status === 'approved' && canManagePurchases()) { <div class="workflow-action"><div><strong>Cotação aprovada</strong><span>A compra ainda não altera o estoque.</span></div><button class="primary" [disabled]="saving()" (click)="placeOrder()">Registrar pedido ao fornecedor</button></div> }
            @if (purchase.notes) { <section class="purchase-notes"><span class="eyebrow">Observações internas</span><p>{{ purchase.notes }}</p></section> }
            <section class="purchase-form-section"><div class="section-heading"><div><p class="eyebrow">Documentação</p><h3>Documentos anexados</h3></div>@if (canManagePurchases()) { <label class="attachment-inline">+ Anexar documentos<input type="file" multiple (change)="uploadAttachments(purchase, $any($event.target).files)" /></label> }</div>@if (purchase.attachments.length) { <div class="attachment-list">@for (attachment of purchase.attachments; track attachment.id) { <button type="button" class="attachment-row" (click)="downloadAttachment(purchase, attachment)"><span>📎 {{ attachment.filename }}</span><small>{{ formatBytes(attachment.size_bytes) }}</small></button> }</div> } @else { <p class="muted">Nenhum documento anexado ainda.</p> }</section>
          </div>
          <aside class="purchase-aside"><section class="purchase-aside-card"><p class="eyebrow">Resumo</p><div><span>Itens</span><strong>{{ purchase.items.length }}</strong></div><div><span>Unidades pedidas</span><strong>{{ totalUnits(purchase) | number:'1.0-3' }}</strong></div><div><span>Recebidas</span><strong>{{ receivedUnits(purchase) | number:'1.0-3' }}</strong></div>@if (selectedQuote(purchase); as quote) { <div><span>Fornecedor escolhido</span><strong>{{ quote.supplier_name }}</strong></div><div><span>Valor acordado</span><strong>{{ quote.total | currency:'BRL' }}</strong></div> }</section>
            <section class="purchase-aside-card timeline-card"><p class="eyebrow">Histórico da compra</p>@for (event of purchase.events; track event.id) { <div class="purchase-event"><i></i><div><strong>{{ event.detail }}</strong><small>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</small></div></div> }</section>
            @if (canManagePurchases() && purchase.status !== 'received' && purchase.status !== 'cancelled') { <button type="button" class="cancel-purchase" (click)="cancel()">Cancelar compra</button> }
          </aside>
        </div>
        @if (error()) { <p class="purchase-error" role="alert">{{ error() }}</p> }
      </section></div>
    }
  `,
  styleUrl: './purchases.scss',
})
export class PurchasesPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  readonly purchases = signal<Purchase[]>([]);
  canManagePurchases() { return canManagePurchases(this.auth.user()?.role); }
  canAdjustStock() { return canAdjustStock(this.auth.user()?.role); }
  canReadCosts() { return canReadCosts(this.auth.user()?.role); }
  readonly products = signal<Product[]>([]);
  readonly detail = signal<Purchase | null>(null);
  readonly showNew = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly search = signal('');
  readonly statusFilter = signal('all');
  readonly receiveValues = signal<Record<string, { quantity: number; productId: string; create: boolean }>>({});
  readonly receiptIds = signal<Record<string, string>>({});
  readonly quoteCosts = signal<Record<string, number>>({});
  readonly itemCostDrafts = signal<Record<string, { base_unit_cost: number; freight_amount: number; tax_amount: number; discount_amount: number }>>({});
  readonly selectedFiles = signal<File[]>([]);
  readonly expenseCategories = ['Aluguel', 'Energia e água', 'Internet e telefonia', 'Contabilidade', 'Marketing', 'Frete e transporte', 'Material de escritório', 'Impostos e taxas', 'Serviços', 'Outros'];
  private readonly initialRange = quickDateRange('last30');
  readonly startDate = signal(this.initialRange.startDate);
  readonly endDate = signal(this.initialRange.endDate);
  readonly statuses: { value: string; label: string }[] = [
    { value: 'negotiating', label: 'Em negociação' }, { value: 'approved', label: 'Aprovada' },
    { value: 'ordered', label: 'Pedido enviado' }, { value: 'partially_received', label: 'Recebimento parcial' },
    { value: 'received', label: 'Recebida' }, { value: 'cancelled', label: 'Cancelada' },
  ];
  readonly workflow = [{ value: 'negotiating', label: 'Negociação' }, { value: 'approved', label: 'Aprovação' }, { value: 'ordered', label: 'Pedido' }, { value: 'received', label: 'Recebimento' }];
  readonly form = this.fb.group({
    purchase_type: ['parts'], supplier_name: [''], expense_category: [''], expense_amount: [0, [Validators.min(0)]], needed_by: [''], notes: [''], items: this.fb.array([this.newLine()]),
  });
  readonly quoteForm = this.fb.nonNullable.group({ supplier_name: ['', Validators.required], supplier_contact: [''], freight_amount: [0, [Validators.required, Validators.min(0)]], tax_amount: [0, [Validators.required, Validators.min(0)]], discount_amount: [0, [Validators.required, Validators.min(0)]], allocation_method: ['proportional' as 'proportional' | 'quantity'], delivery_days: [null as number | null], payment_terms: [''], notes: [''] });
  readonly lines = this.form.controls.items as FormArray;
  readonly periodPurchases = computed(() => {
    const startDate = this.startDate();
    const endDate = this.endDate();
    return this.purchases().filter((purchase) => {
      const date = this.purchaseLocalDate(purchase);
      return (!startDate || date >= startDate) && (!endDate || date <= endDate);
    });
  });
  readonly filtered = computed(() => {
    const term = this.search().trim().toLocaleLowerCase('pt-BR');
    return this.periodPurchases().filter((purchase) => {
      const matchStatus = this.statusFilter() === 'all' || purchase.status === this.statusFilter();
      const haystack = [purchase.number, ...purchase.items.flatMap((item) => [item.sku, item.description]), ...purchase.quotes.map((quote) => quote.supplier_name)].join(' ').toLocaleLowerCase('pt-BR');
      return matchStatus && (!term || haystack.includes(term));
    });
  });
  readonly summary = computed(() => [
    { status: 'negotiating', label: 'Em negociação', count: this.periodPurchases().filter((p) => p.status === 'negotiating').length, note: 'Aguardando propostas' },
    { status: 'ordered', label: 'Pedidos em aberto', count: this.periodPurchases().filter((p) => ['ordered', 'partially_received'].includes(p.status)).length, note: 'Aguardando recebimento' },
    { status: 'received', label: 'Recebidas', count: this.periodPurchases().filter((p) => p.status === 'received').length, note: 'Estoque atualizado' },
  ]);

  private purchaseLocalDate(purchase: Purchase) {
    const date = new Date(purchase.created_at);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  }

  ngOnInit() { this.load(); this.api.products().subscribe({ next: (items) => this.products.set(items), error: () => undefined }); }
  private newLine() { return this.fb.group({ product_id: [''], sku: ['', Validators.required], description: ['', Validators.required], quantity: [1, [Validators.required, Validators.min(0.001)]] }); }
  load() { this.api.purchases().subscribe({ next: (items) => this.purchases.set(items), error: () => this.error.set('Não foi possível carregar as compras. Tente novamente.') }); }
  applyPeriod(range: DateRange) { this.startDate.set(range.startDate); this.endDate.set(range.endDate); }
  toggleStatus(status: string) { this.statusFilter.set(this.statusFilter() === status ? 'all' : status); }
  openNew() { this.error.set(''); this.selectedFiles.set([]); this.form.reset({ purchase_type: 'parts', supplier_name: '', expense_category: '', expense_amount: 0, needed_by: '', notes: '' }); while (this.lines.length) this.lines.removeAt(0); this.addLine(); this.showNew.set(true); }
  addLine() { this.lines.push(this.newLine()); }
  removeLine(index: number) { this.lines.removeAt(index); }
  selectProduct(index: number, id: string) { const line = this.lines.at(index); const product = this.products().find((entry) => entry.id === id); if (product) line.patchValue({ product_id: id, sku: product.sku, description: product.name }); else line.patchValue({ product_id: '', sku: '', description: '' }); }
  create() {
    const isExpense = this.form.controls.purchase_type.value === 'expense';
    if (this.saving() || (!isExpense && this.form.invalid) || (isExpense && (!this.form.controls.expense_category.value || Number(this.form.controls.expense_amount.value) < 0))) return;
    this.saving.set(true); this.error.set('');
    const value = this.form.getRawValue();
    this.api.createPurchase({ purchase_type: value.purchase_type, supplier_name: value.supplier_name || null, expense_category: value.expense_category || null, expense_amount: value.expense_amount || null, needed_by: value.needed_by || null, notes: value.notes || null, items: value.purchase_type === 'expense' ? [] : value.items.map((item) => ({ ...item, product_id: item.product_id || null })) }).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (purchase) => { this.showNew.set(false); this.purchases.update((list) => [purchase, ...list]); const files = this.selectedFiles(); if (files.length) { this.api.uploadPurchaseAttachments(purchase.id, files).subscribe({ next: (updated) => this.setPurchase(updated) }); } this.openDetails(purchase); }, error: (err) => this.error.set(err.error?.detail || 'Não foi possível salvar a compra.') });
  }
  itemCost(item: PurchaseItem, field: 'base_unit_cost' | 'freight_amount' | 'tax_amount' | 'discount_amount') { return this.itemCostDrafts()[item.id]?.[field] ?? (field === 'base_unit_cost' ? item.base_unit_cost ?? item.unit_cost ?? 0 : item[field] ?? 0); }
  setItemCost(item: PurchaseItem, field: 'base_unit_cost' | 'freight_amount' | 'tax_amount' | 'discount_amount', value: string) { this.itemCostDrafts.update((drafts) => ({ ...drafts, [item.id]: { base_unit_cost: this.itemCost(item, 'base_unit_cost'), freight_amount: this.itemCost(item, 'freight_amount'), tax_amount: this.itemCost(item, 'tax_amount'), discount_amount: this.itemCost(item, 'discount_amount'), [field]: Number(value) } })); }
  saveItemCosts(purchase: Purchase, item: PurchaseItem) { const draft = this.itemCostDrafts()[item.id]; if (!draft || this.saving()) return; this.saving.set(true); this.error.set(''); this.api.updatePurchaseItem(purchase.id, item.id, draft).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => this.setPurchase(updated), error: (err) => this.error.set(err.error?.detail || 'Não foi possível atualizar o custo da peça.') }); }
  setAttachments(files: FileList | null) { this.selectedFiles.set(files ? Array.from(files).slice(0, 10) : []); }
  uploadAttachments(purchase: Purchase, files: FileList | null) { const selected = files ? Array.from(files).slice(0, 10) : []; if (!selected.length) return; this.saving.set(true); this.api.uploadPurchaseAttachments(purchase.id, selected).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => this.setPurchase(updated), error: (err) => this.error.set(err.error?.detail || 'Não foi possível anexar os documentos.') }); }
  downloadAttachment(purchase: Purchase, attachment: Purchase['attachments'][number]) { this.api.downloadPurchaseAttachment(purchase.id, attachment.id, attachment.filename); }
  formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`; }
  openDetails(purchase: Purchase) { this.error.set(''); this.receiveValues.set(Object.fromEntries(purchase.items.map((item) => [item.id, { quantity: Math.max(0, item.quantity - item.received_quantity), productId: item.product_id || '', create: !item.product_id }]))); this.quoteCosts.set(Object.fromEntries(purchase.items.map((item) => [item.id, 0]))); this.itemCostDrafts.set(Object.fromEntries(purchase.items.map((item) => [item.id, { base_unit_cost: item.base_unit_cost ?? item.unit_cost ?? 0, freight_amount: item.freight_amount ?? 0, tax_amount: item.tax_amount ?? 0, discount_amount: item.discount_amount ?? 0 }]))); this.detail.set(purchase); }
  selectedQuote(purchase: Purchase) { return purchase.quotes.find((quote) => quote.id === purchase.selected_quote_id) ?? null; }
  statusLabel(status: PurchaseStatus) { return this.statuses.find((entry) => entry.value === status)?.label ?? status; }
  stepIndex(status: PurchaseStatus) { if (status === 'cancelled') return -1; if (status === 'received') return 4; if (status === 'partially_received') return 3; return ['negotiating', 'approved', 'ordered'].indexOf(status); }
  progress(item: PurchaseItem) { return item.quantity ? Math.min(100, item.received_quantity / item.quantity * 100) : 0; }
  totalUnits(purchase: Purchase) { return purchase.items.reduce((sum, item) => sum + item.quantity, 0); }
  receivedUnits(purchase: Purchase) { return purchase.items.reduce((sum, item) => sum + item.received_quantity, 0); }
  receiveQty(item: PurchaseItem) { return this.receiveValues()[item.id]?.quantity ?? 0; }
  setReceiveQty(item: PurchaseItem, value: string) { this.receiveValues.update((values) => ({ ...values, [item.id]: { ...values[item.id], quantity: Number(value) } })); this.clearReceiptId(item); }
  receiveProduct(item: PurchaseItem) { return this.receiveValues()[item.id]?.productId ?? ''; }
  setReceiveProduct(item: PurchaseItem, value: string) { this.receiveValues.update((values) => ({ ...values, [item.id]: { ...values[item.id], productId: value, create: false } })); this.clearReceiptId(item); }
  createNewProduct(item: PurchaseItem) { return this.receiveValues()[item.id]?.create ?? false; }
  setCreateNewProduct(item: PurchaseItem, value: boolean) { this.receiveValues.update((values) => ({ ...values, [item.id]: { ...values[item.id], create: value, productId: value ? '' : values[item.id]?.productId ?? '' } })); this.clearReceiptId(item); }
  quoteUnitCost(item: PurchaseItem) { return this.quoteCosts()[item.id] ?? 0; }
  quoteSubtotal(purchase: Purchase) { return purchase.items.reduce((sum, item) => sum + this.quoteUnitCost(item) * item.quantity, 0); }
  quoteTotal(purchase: Purchase) { const value = this.quoteForm.getRawValue(); return this.quoteSubtotal(purchase) + Number(value.freight_amount || 0) + Number(value.tax_amount || 0) - Number(value.discount_amount || 0); }
  setQuoteUnitCost(item: PurchaseItem, value: string) { this.quoteCosts.update((costs) => ({ ...costs, [item.id]: Number(value) })); }
  quoteCostsComplete(purchase: Purchase) { return purchase.items.every((item) => Number.isFinite(this.quoteUnitCost(item)) && this.quoteUnitCost(item) >= 0); }
  addQuote() { const purchase = this.detail(); if (!purchase || this.quoteForm.invalid || !this.quoteCostsComplete(purchase) || this.quoteTotal(purchase) < 0 || this.saving()) return; this.saving.set(true); this.error.set(''); const value = this.quoteForm.getRawValue(); this.api.addPurchaseQuote(purchase.id, { ...value, total: this.quoteTotal(purchase), item_costs: this.quoteCosts() }).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => { this.setPurchase(updated); this.quoteForm.reset({ supplier_name: '', supplier_contact: '', freight_amount: 0, tax_amount: 0, discount_amount: 0, allocation_method: 'proportional', delivery_days: null, payment_terms: '', notes: '' }); this.quoteCosts.set(Object.fromEntries(purchase.items.map((item) => [item.id, 0]))); }, error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar a cotação.') }); }
  selectQuote(id: string) { const purchase = this.detail(); if (!purchase || this.saving()) return; if (!confirm('Aprovar esta cotação? A compra seguirá para envio do pedido ao fornecedor.')) return; this.runAction(this.api.selectPurchaseQuote(purchase.id, id)); }
  placeOrder() { const purchase = this.detail(); if (purchase) this.runAction(this.api.placePurchaseOrder(purchase.id)); }
  receive(item: PurchaseItem) {
    const purchase = this.detail();
    if (!purchase || this.saving()) return;
    const choice = this.receiveValues()[item.id];
    if (!choice || choice.quantity <= 0) return;
    const receiptId = this.receiptIds()[item.id] ?? crypto.randomUUID();
    this.receiptIds.update((ids) => ({ ...ids, [item.id]: receiptId }));
    this.saving.set(true); this.error.set('');
    this.api.receivePurchase(purchase.id, { items: [{ item_id: item.id, receipt_id: receiptId, quantity: choice.quantity, product_id: choice.productId || null, create_product: choice.create }] }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.setPurchase(updated); this.clearReceiptId(item); this.api.products().subscribe((items) => this.products.set(items)); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar o recebimento.')
    });
  }
  private clearReceiptId(item: PurchaseItem) { this.receiptIds.update((ids) => { const updated = { ...ids }; delete updated[item.id]; return updated; }); }
  cancel() { const purchase = this.detail(); if (!purchase || this.saving()) return; if (!confirm(`Cancelar ${purchase.number}? Essa ação não poderá ser desfeita.`)) return; this.runAction(this.api.cancelPurchase(purchase.id)); }
  private runAction(request: ReturnType<ApiService['placePurchaseOrder']>) { const purchase = this.detail(); if (!purchase) return; this.saving.set(true); this.error.set(''); request.pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => { this.setPurchase(updated); if (updated.status === 'received') this.api.products().subscribe((items) => this.products.set(items)); }, error: (err) => this.error.set(err.error?.detail || 'Não foi possível atualizar esta compra.') }); }
  private setPurchase(purchase: Purchase) { this.itemCostDrafts.set(Object.fromEntries(purchase.items.map((item) => [item.id, { base_unit_cost: item.base_unit_cost ?? item.unit_cost ?? 0, freight_amount: item.freight_amount ?? 0, tax_amount: item.tax_amount ?? 0, discount_amount: item.discount_amount ?? 0 }]))); this.detail.set(purchase); this.purchases.update((items) => items.map((item) => item.id === purchase.id ? purchase : item)); }
}
