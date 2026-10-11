import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { debounceTime } from 'rxjs';
import { CurrencyPipe, DatePipe, DecimalPipe } from '@angular/common';
import { Component, DestroyRef, OnInit, computed, inject, signal } from '@angular/core';
import { FormArray, FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { PaymentConditionType, Product, Purchase, PurchaseItem, PurchasePayable, PurchaseQuote, PurchaseStatus } from '../../core/models';
import { canAdjustStock, canManageCatalog, canManagePurchases, canReadCosts } from '../../core/user-access';
import { DateRange, quickDateRange } from '../../core/quick-date-ranges';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';
import { MoneyInputDirective } from '../../shared/money-input.directive';
import { dateOnlyLabel, dateOnlyValue } from '../../shared/date-only';

@Component({
  selector: 'app-purchases',
  imports: [CurrencyPipe, DatePipe, DecimalPipe, FormsModule, MoneyInputDirective, ReactiveFormsModule, PageHeader, PeriodFilter],
  template: `
    <app-page-header eyebrow="Suprimentos" title="Compras" subtitle="Peças para o estoque e despesas operacionais da empresa.">
      @if (canManagePurchases()) { <div class="purchase-header-actions"><button class="secondary" type="button" [disabled]="importLoading()" (click)="purchaseImportInput.click()">{{ importLoading() ? 'Analisando documento…' : 'Importar documento' }}</button><button class="primary" type="button" (click)="openNew()">+ Nova compra</button><input #purchaseImportInput hidden type="file" accept=".pdf,.xml,.jpg,.jpeg,.png,application/pdf,image/jpeg,image/png,application/xml,text/xml" (change)="onImportDocument($event)" /></div> }
    </app-page-header>
    @if (importError() && !importReview()) { <p class="purchase-error" role="alert">{{ importError() }}</p> }
    @if (message()) { <p class="purchase-success" role="status">{{ message() }}</p> }
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
      @if (selectedPurchases().length) { <button type="button" class="danger-outline" [disabled]="saving()" (click)="deleteSelectedDrafts()">Excluir {{ selectedPurchases().length }} rascunho(s)</button> }
      @if (totalPages() > 1) { <span class="purchase-pages"><button type="button" class="secondary small" [disabled]="page() <= 1" (click)="goToPage(-1)">Anterior</button><small>página {{ page() }} de {{ totalPages() }}</small><button type="button" class="secondary small" [disabled]="page() >= totalPages()" (click)="goToPage(1)">Próxima</button></span> }
    </section>
    <section class="card purchase-table-card" [class.restricted-costs]="!canReadCosts()">
      <div class="table-wrap" (scroll)="closeRowMenu()"><table><thead><tr><th></th><th>COMPRA</th><th>PEÇAS</th><th>FORNECEDOR / COTAÇÕES</th><th>ETAPA</th><th>PREVISÃO</th><th>VALOR</th><th>ABERTA EM</th><th></th></tr></thead><tbody>
        @for (purchase of pagedPurchases(); track purchase.id) {
          <tr class="purchase-row" tabindex="0" (click)="openDetails(purchase)" (keydown.enter)="openDetails(purchase)">
            <td class="row-select">@if (isSelectable(purchase)) { <input type="checkbox" [checked]="isSelected(purchase.id)" [attr.aria-label]="'Selecionar ' + purchase.number" (click)="$event.stopPropagation()" (change)="toggleSelection(purchase.id)" /> }</td>
            <td><strong>{{ purchase.number }}</strong><small>{{ purchase.purchase_type === 'expense' ? 'Despesa da empresa' : (purchase.items.length + (purchase.items.length === 1 ? ' item' : ' itens')) }}</small></td>
            <td><div class="purchase-products">@if (purchase.purchase_type === 'expense') { <span>{{ purchase.expense_category }}</span><small>{{ purchase.expense_amount | currency:'BRL' }}</small> } @else { @for (item of purchase.items.slice(0, 2); track item.id) { <span>{{ item.description }}</span> } @if (purchase.items.length > 2) { <small>+{{ purchase.items.length - 2 }} outras</small> } }</div></td>
            <td>@if (purchase.purchase_type === 'expense') { <strong>{{ purchase.supplier_name || 'Sem fornecedor' }}</strong><small>Despesa lançada</small> } @else if (selectedQuote(purchase); as quote) { <strong>{{ quote.supplier_name }}</strong><small>{{ quote.total | currency:'BRL' }} · cotação escolhida</small> } @else { <strong [class.muted]="!purchase.supplier_name">{{ purchase.supplier_name || 'Em cotação' }}</strong><small>{{ purchase.supplier_name ? 'Fornecedor informado' : purchase.quotes.length + (purchase.quotes.length === 1 ? ' proposta registrada' : ' propostas registradas') }}</small> }</td>
            <td><span class="purchase-badge" [attr.data-status]="purchase.status">{{ purchaseStatusLabel(purchase) }}</span></td>
            <td>{{ purchase.needed_by ? dateOnly(purchase.needed_by) : '—' }}@if (isOverdue(purchase)) { <small class="overdue-chip">Atrasada</small> }</td><td>{{ purchaseTotal(purchase) | currency:'BRL' }}</td><td>{{ purchase.created_at | date:'dd/MM/yyyy' }}</td><td class="row-action"><button type="button" class="row-open" (click)="$event.stopPropagation(); openDetails(purchase)">Abrir <span>→</span></button><div class="purchase-row-menu"><button type="button" class="row-menu-trigger" [attr.aria-label]="'Ações da compra ' + purchase.number" [attr.aria-expanded]="rowMenuId() === purchase.id" aria-haspopup="menu" (click)="toggleRowMenu(purchase.id, $event)">⋮</button></div></td>
          </tr>
        } @empty { <tr><td colspan="9"><div class="purchase-empty"><strong>Nenhuma compra neste período</strong><span>Comece uma negociação para acompanhar propostas e recebimentos por aqui.</span>@if (canManagePurchases()) { <button class="secondary" (click)="openNew()">Criar compra</button> }</div></td></tr> }
      </tbody></table></div>
    </section>
    @if (rowMenuPurchase(); as purchase) { <div class="purchase-row-menu-popover" role="menu" [style.top.px]="rowMenuPosition()?.top" [style.left.px]="rowMenuPosition()?.left"><button type="button" role="menuitem" (click)="copyPurchaseFromList(purchase, $event)">Copiar</button>@if (canManagePurchases()) { <button type="button" role="menuitem" class="menu-danger" (click)="requestDelete(purchase, $event)">Excluir compra</button> }</div> }
    @if (deleteTarget(); as target) {
      <div class="modal-backdrop" (click)="cancelDelete()"><section class="modal purchase-modal delete-modal" role="dialog" aria-modal="true" [attr.aria-label]="'Excluir compra ' + target.number" (click)="$event.stopPropagation()">
        <div class="modal-head"><div><p class="eyebrow">Suprimentos · {{ target.number }}</p><h2>Excluir compra</h2><p class="modal-intro">{{ target.supplier_name || 'Sem fornecedor' }} · {{ purchaseTotal(target) | currency:'BRL' }} · esta ação não pode ser desfeita.</p></div><button class="close" aria-label="Fechar" (click)="cancelDelete()">×</button></div>
        <p class="delete-lead">Serão apagados junto com o pedido:</p>
        <ul class="delete-effects">@for (effect of deletionEffects(target); track effect) { <li>{{ effect }}</li> }</ul>
        @if (deleteBlockedByPayment(target)) { <p class="purchase-error" role="alert">Este pedido tem pagamento registrado no título a pagar. Excluir apagaria uma saída de dinheiro já feita — use <strong>Cancelar compra</strong> com estorno para manter o registro financeiro.</p> }
        <label>Motivo (opcional)<input type="text" maxlength="255" [value]="deleteReason()" (input)="deleteReason.set($any($event.target).value)" placeholder="Ex.: pedido criado por engano" /></label>
        <p class="delete-note">A exclusão fica registrada na auditoria com número, fornecedor, itens, valor, autor e data. O estoque recebido volta por movimento de estorno.</p>
        <div class="purchase-form-actions"><button type="button" class="secondary" (click)="cancelDelete()">Cancelar</button><button type="button" class="danger-outline" [disabled]="saving() || deleteBlockedByPayment(target)" (click)="confirmDelete(target)">{{ saving() ? 'Excluindo…' : 'Excluir compra' }}</button></div>
      </section></div>
    }

    @if (importReview(); as review) {
      <div class="modal-backdrop" (click)="closeImportReview()"><section class="modal wide purchase-modal purchase-import-review" role="dialog" aria-modal="true" aria-labelledby="purchase-import-title" (click)="$event.stopPropagation()">
        <div class="modal-head"><div><p class="eyebrow">Importação assistida · {{ review.filename }}</p><h2 id="purchase-import-title">Revise antes de criar a compra</h2><p class="modal-intro">A extração é uma sugestão. Confira os campos e valores no documento original.</p></div><button class="close" aria-label="Fechar revisão" (click)="closeImportReview()">×</button></div>
        @if (review.warnings?.length) { <div class="purchase-import-warnings" role="status"><strong>Confira estes pontos</strong><ul>@for (warning of review.warnings; track warning) { <li>{{ warning }}</li> }</ul></div> }
        <div class="purchase-form-meta import-meta">
          <label>Perfil do documento<select [ngModel]="review.profile.profile_id || ''" [ngModelOptions]="{standalone: true}" (ngModelChange)="changeImportProfile($event)"><option value="">Não identificado</option>@for (profile of importProfiles(); track profile.profile_id) { <option [value]="profile.profile_id">{{ profile.name }}</option> }</select><small>@if (review.profile.selected) { Perfil escolhido manualmente · sempre revise antes de salvar } @else { {{ review.profile.confidence * 100 | number:'1.0-0' }}% de evidência automática · sempre revise antes de salvar }</small>@if (importLoading()) { <small role="status">Reanalisando com o perfil selecionado…</small> }</label>
          <label>Fornecedor<input [value]="importDraft().supplier" (input)="updateImportField('supplier', $any($event.target).value)" placeholder="Conferir fornecedor" />@if (review.fields.supplier) { <small>{{ fieldOrigin(review.fields.supplier) }}</small> }</label>
          <label>Número do pedido<input [value]="importDraft().orderNumber" (input)="updateImportField('orderNumber', $any($event.target).value)" placeholder="Opcional" />@if (review.fields.order_number) { <small>{{ fieldOrigin(review.fields.order_number) }}</small> }</label>
          <label>Data do documento<input [value]="importDraft().documentDate" (input)="updateImportField('documentDate', $any($event.target).value)" placeholder="Como aparece no recibo" />@if (review.fields.date) { <small>{{ fieldOrigin(review.fields.date) }}</small> }</label>
          <label>Total do documento<input appMoneyInput [appMoneyInput]="importDraft().total" min="0" (moneyInput)="updateImportNumber('total', $event)" (moneyValidity)="setImportMoneyValidity('total', $event)" />@if (review.fields.total) { <small>{{ fieldOrigin(review.fields.total) }}</small> }</label>
          <label>Frete identificado<input appMoneyInput [appMoneyInput]="importDraft().shipping" min="0" (moneyInput)="updateImportNumber('shipping', $event)" (moneyValidity)="setImportMoneyValidity('shipping', $event)" />@if (review.fields.shipping) { <small>{{ fieldOrigin(review.fields.shipping) }}</small> }</label>
          <label>Desconto identificado<input appMoneyInput [appMoneyInput]="importDraft().discount" min="0" (moneyInput)="updateImportNumber('discount', $event)" (moneyValidity)="setImportMoneyValidity('discount', $event)" />@if (review.fields.discount) { <small>{{ fieldOrigin(review.fields.discount) }}</small> }</label>
          <label>Impostos identificados<input appMoneyInput [appMoneyInput]="importDraft().tax" min="0" (moneyInput)="updateImportNumber('tax', $event)" (moneyValidity)="setImportMoneyValidity('tax', $event)" />@if (review.fields.tax) { <small>{{ fieldOrigin(review.fields.tax) }}</small> }</label>
        </div>
        <div class="purchase-form-section"><div class="section-heading"><div><p class="eyebrow">Campos extraídos</p><h3>Itens da compra</h3></div><button type="button" class="secondary small" (click)="addImportLine()">+ Adicionar linha</button></div>
          <p class="purchase-flow-hint">Campos sem evidência não são inventados. Compare quantidade × unitário com o total da linha e com o total do recibo.</p>
          <div class="purchase-line-list import-line-list">@for (item of importDraft().items; track $index; let i = $index) {
            <div class="purchase-line-form import-line">
              <label class="line-description">Descrição<input [value]="item.description" (input)="updateImportItem(i, 'description', $any($event.target).value)" /></label>
              <label>SKU / código<input [value]="item.sku" (input)="updateImportItem(i, 'sku', $any($event.target).value)" placeholder="Opcional" /></label>
              <label class="import-stock-control"><input type="checkbox" [checked]="item.stock_controlled" (change)="setImportStockControlled(i, $any($event.target).checked)" /> Controlado no estoque</label>
              <div class="import-product-search"><label>Produto do estoque<input [value]="importProductSearch()[i] || ''" (input)="searchImportProducts(i, $any($event.target).value)" placeholder="Buscar nome, SKU ou código de barras" autocomplete="off" /></label>
                <div class="import-product-results" [hidden]="!importProductSearch()[i]">
                  @for (product of importProductResults()[i] || []; track product.id) {
                    <button type="button" (click)="selectImportedProduct(i, product)"><strong>{{ product.name }}</strong><small>SKU {{ product.sku }} · EAN {{ product.barcode || 'sem código' }} · {{ product.current_stock | number:'1.0-3' }} un. em estoque</small></button>
                  }
                  @if (importProductSearch()[i] && !(importProductResults()[i] || []).length) { <small>Nenhum produto encontrado. Confira nome, SKU e código.</small> }
                </div>
                @if (item.stock_controlled && item.product_id) { <small>Vinculado: {{ selectedImportProduct(item.product_id)?.sku }} · {{ selectedImportProduct(item.product_id)?.name }} <button type="button" class="text-button" (click)="clearImportedProduct(i)">Remover vínculo</button></small> }
                @if (canManageCatalog()) { <button type="button" class="secondary small" [disabled]="!item.stock_controlled" (click)="openImportProductCreate(i)">+ Cadastrar produto</button> }
              </div>
              <label>Quantidade<input type="number" min="0.001" step="0.001" [value]="item.quantity" (input)="updateImportItem(i, 'quantity', $any($event.target).value)" /></label>
              <label>Valor unitário<input appMoneyInput [appMoneyInput]="item.unit_cost" min="0" (moneyInput)="updateImportItem(i, 'unit_cost', $event)" (moneyValidity)="setImportMoneyValidity('item-' + i, $event)" /></label>
              <label>Desconto da linha<input appMoneyInput [appMoneyInput]="item.discount_amount" min="0" (moneyInput)="updateImportItem(i, 'discount_amount', $event)" (moneyValidity)="setImportMoneyValidity('discount-' + i, $event)" /></label><small>Total da linha: {{ item.line_total | currency:'BRL' }}</small>
              <small class="import-confidence">{{ itemOrigin(item) }}</small>
              <button type="button" class="remove-line" [attr.aria-label]="'Remover item ' + (i + 1)" (click)="removeImportLine(i)">×</button>
            </div>
          } @empty { <p class="muted">Nenhum item detectado. Adicione as linhas manualmente para continuar.</p> }</div>
        </div>
        @if (importError()) { <p class="purchase-error" role="alert">{{ importError() }}</p> }
        @if (importDuplicate(); as duplicate) { <p class="purchase-error" role="alert">Este documento já foi importado na compra <strong>{{ duplicate.purchase_number }}</strong>@if (duplicate.cancelled) { , que está cancelada — você pode continuar. } @else { . Abra a compra existente antes de criar outra. }</p> }
        <section class="import-check">
          <p class="eyebrow">Lançamento</p>
          <div class="import-check-grid">
            <span>Tipo</span><label><select [value]="importType()" (change)="setImportType($any($event.target).value)"><option value="parts">Peças para estoque</option><option value="expense">Despesa da empresa</option></select></label>
            @if (importType() === 'expense') { <span>Categoria da despesa</span><label><select [value]="importCategory()" (change)="importCategory.set($any($event.target).value)">@for (category of expenseCategories; track category) { <option [value]="category">{{ category }}</option> }</select></label> }
            <span>Já pago no checkout</span><label class="check-field"><input type="checkbox" [checked]="importPaidNow()" (change)="setImportPaidNow($any($event.target).checked)" /> o título nasce baixado</label>
            @if (importPaidNow()) { <span>Data do pagamento</span><label><input type="date" [value]="importPaidDate()" (input)="importPaidDate.set($any($event.target).value)" /></label><span>Forma do pagamento</span><label><input type="text" [value]="importPaidMethod()" (input)="importPaidMethod.set($any($event.target).value)" placeholder="Visa, Google Pay…" /></label> }
          </div>
          @if (!importDraft().items.length && review.candidates?.length) {
            <div class="import-candidates"><p class="eyebrow">Nenhum item reconhecido</p><p class="muted">Marque uma linha do documento como item para começar a revisão.</p><ul>@for (candidate of review.candidates; track candidate.text) { <li><span>{{ candidate.text }}</span><button type="button" class="secondary small" (click)="useImportCandidate(candidate)">Usar como item</button></li> }</ul></div>
          }
        </section>
        <section class="import-check">
          <p class="eyebrow">Conferência do documento</p>
          <div class="import-check-grid">
            <span>Moeda lida</span><strong>{{ importDraft().currency || 'não identificada' }}</strong>
            <span>Cotação usada (1 unidade da moeda em R$)</span>
            @if (importNeedsRate() || importDraft().exchangeRate !== null) { <input type="number" min="0" step="0.000001" [value]="importDraft().exchangeRate ?? ''" (input)="setImportRateFromInput($any($event.target).value)" placeholder="Obrigatória" /> } @else { <strong>não se aplica</strong> }
            <span>Valor efetivamente pago</span><label class="import-paid"><input appMoneyInput [appMoneyInput]="importDraft().paidAmount ?? 0" min="0" (moneyInput)="setImportPaid($event)" />@if (importDraft().paidAmount === null) { <small class="muted">não identificado</small> }</label>
            <span>Diferença paga ÷ total</span><strong [class.check-warn]="importPaidDifference() > 0.05 || importPaidDifference() < -0.05">{{ importPaidDifference() | currency:'BRL' }}</strong>
            <span>Fechamento: itens + frete + impostos − descontos − total</span>@if (importHasItemsToCheck()) { <strong [class.check-warn]="importClosingDifference() > 0.05 || importClosingDifference() < -0.05">{{ importClosingDifference() | currency:'BRL' }}</strong> } @else { <strong class="muted">sem itens lidos para conferir</strong> }
          </div>
          <details class="import-text"><summary>Ver o que foi lido</summary>@if (review.text) { <pre>{{ review.text }}</pre> } @else { <p class="muted">Este formato não devolve texto de leitura (por exemplo, XML de NF-e).</p> }</details>
        </section>
        <div class="purchase-form-actions"><span class="muted">O arquivo original será anexado. Nenhum estoque será movimentado.</span><div class="import-review-actions"><button type="button" class="secondary" (click)="closeImportReview()">Cancelar</button><button type="button" class="primary" [disabled]="creatingImport() || !canConfirmImport()" (click)="createImportedPurchase()">{{ creatingImport() ? 'Criando…' : 'Confirmar e criar compra' }}</button></div></div>
      </section></div>
    }

    @if (importProductModal()) {
      <div class="modal-backdrop import-product-backdrop" (click)="closeImportProductCreate()"><section class="modal purchase-modal import-product-modal" role="dialog" aria-modal="true" aria-labelledby="import-product-title" (click)="$event.stopPropagation()"><div class="modal-head"><div><p class="eyebrow">Catálogo · nova peça</p><h2 id="import-product-title">Cadastrar e vincular produto</h2><p class="modal-intro">Preencha os mesmos dados básicos exigidos no catálogo. O cadastro só será criado ao confirmar.</p></div><button class="close" type="button" aria-label="Fechar" (click)="closeImportProductCreate()">×</button></div><div class="purchase-form-meta"><label>Tipo de estoque<select [value]="importProductDraft().stock_type" (change)="updateImportProduct('stock_type', $any($event.target).value)"><option value="product">Produto</option><option value="warehouse">Almoxarifado</option></select></label><label>SKU *<input [value]="importProductDraft().sku" (input)="updateImportProduct('sku', $any($event.target).value)" /></label><label>Nome *<input [value]="importProductDraft().name" (input)="updateImportProduct('name', $any($event.target).value)" /></label><label>Marca<input [value]="importProductDraft().brand" (input)="updateImportProduct('brand', $any($event.target).value)" /></label><label>Fabricante<input [value]="importProductDraft().manufacturer" (input)="updateImportProduct('manufacturer', $any($event.target).value)" /></label><label>Número OEM / MPN<input [value]="importProductDraft().manufacturer_part_number" (input)="updateImportProduct('manufacturer_part_number', $any($event.target).value)" /></label><label>GTIN / código de barras<input [value]="importProductDraft().barcode" (input)="updateImportProduct('barcode', $any($event.target).value)" /></label><label>Categoria<input [value]="importProductDraft().category" (input)="updateImportProduct('category', $any($event.target).value)" /></label><label>Condição<select [value]="importProductDraft().item_condition" (change)="updateImportProduct('item_condition', $any($event.target).value)"><option value="new">Nova</option><option value="used">Usada</option><option value="refurbished">Recondicionada</option></select></label><label>Garantia (dias)<input type="number" min="0" max="3650" [value]="importProductDraft().warranty_days ?? ''" (input)="updateImportProduct('warranty_days', $any($event.target).value)" /></label><label>País de origem<input [value]="importProductDraft().origin_country" (input)="updateImportProduct('origin_country', $any($event.target).value)" /></label><label>Preço de venda<input appMoneyInput [appMoneyInput]="importProductDraft().sale_price" min="0" (moneyInput)="updateImportProduct('sale_price', $event)" /></label>@if (canReadCosts()) { <label>Custo<input appMoneyInput [appMoneyInput]="importProductDraft().cost_price" min="0" (moneyInput)="updateImportProduct('cost_price', $event)" /></label> }<label>Estoque mínimo<input type="number" min="0" step="0.001" [value]="importProductDraft().minimum_stock" (input)="updateImportProduct('minimum_stock', $any($event.target).value)" /></label><label>Peso embalado (g)<input type="number" min="0" step="0.001" [value]="importProductDraft().weight_g ?? ''" (input)="updateImportProduct('weight_g', $any($event.target).value)" /></label><label>Comprimento (cm)<input type="number" min="0" step="0.01" [value]="importProductDraft().package_length_cm ?? ''" (input)="updateImportProduct('package_length_cm', $any($event.target).value)" /></label><label>Largura (cm)<input type="number" min="0" step="0.01" [value]="importProductDraft().package_width_cm ?? ''" (input)="updateImportProduct('package_width_cm', $any($event.target).value)" /></label><label>Altura (cm)<input type="number" min="0" step="0.01" [value]="importProductDraft().package_height_cm ?? ''" (input)="updateImportProduct('package_height_cm', $any($event.target).value)" /></label><label class="notes-field">Descrição<textarea rows="2" [value]="importProductDraft().description" (input)="updateImportProduct('description', $any($event.target).value)"></textarea></label></div>@if (importProductError()) { <p class="purchase-error" role="alert">{{ importProductError() }}</p> }<div class="purchase-form-actions"><span class="muted">Estoque inicial zero · sem movimentação.</span><button type="button" class="primary" [disabled]="savingImportProduct() || !canSaveImportProduct()" (click)="saveImportProduct()">{{ savingImportProduct() ? 'Salvando…' : 'Criar e vincular à linha' }}</button></div></section></div>
    }

    @if (showNew()) {
      <div class="modal-backdrop" (click)="showNew.set(false)"><section class="modal wide purchase-modal" role="dialog" aria-modal="true" aria-labelledby="new-purchase-title" (click)="$event.stopPropagation()">
        <div class="modal-head"><div><p class="eyebrow">Suprimentos</p><h2 id="new-purchase-title">Nova compra</h2><p class="modal-intro">Cadastre peças para o estoque ou uma despesa da empresa com seus documentos.</p></div><button class="close" aria-label="Fechar" (click)="showNew.set(false)">×</button></div>
        <form [formGroup]="form" (ngSubmit)="create()">
<div class="purchase-form-meta"><label>Tipo de lançamento<select formControlName="purchase_type"><option value="parts">Peças para estoque</option><option value="expense">Despesa da empresa</option></select></label><label>Fornecedor / favorecido<input formControlName="supplier_name" list="supplierOptions" placeholder="Nome da empresa ou pessoa" (change)="applySupplierDefaults()" /><datalist id="supplierOptions">@for (supplier of suppliers(); track supplier.id) { <option [value]="supplier.name"></option> }</datalist>@if (supplierByName(form.controls.supplier_name.value); as known) { <small>Cadastrado · {{ known.default_delivery_days ? known.default_delivery_days + ' dias de prazo padrão' : 'sem prazo padrão' }}{{ known.default_payment_terms ? ' · ' + known.default_payment_terms : '' }}</small> } @else if (form.controls.supplier_name.value) { <button type="button" class="secondary small" [disabled]="saving()" (click)="registerSupplier(form.controls.supplier_name.value)">Cadastrar fornecedor</button> }</label><label>Previsão desejada<input type="date" formControlName="needed_by" /></label><label>Nº do pedido do fornecedor<input formControlName="supplier_order_number" placeholder="Opcional" /></label><label>Data do documento<input type="date" formControlName="document_date" /></label><label class="notes-field">Observações<textarea rows="2" formControlName="notes" placeholder="Detalhes do lançamento"></textarea></label></div>
          @if (form.controls.purchase_type.value === 'expense') { <div class="purchase-form-section expense-fields"><div class="section-heading"><div><p class="eyebrow">Despesa operacional</p><h3>Dados do gasto</h3></div></div><div class="purchase-form-meta"><label>Categoria<select formControlName="expense_category"><option value="">Selecione…</option>@for (category of expenseCategories; track category) { <option [value]="category">{{ category }}</option> }</select></label><label>Valor total<input appMoneyInput formControlName="expense_amount" min="0" /></label><label>Condição de pagamento<select formControlName="payment_type"><option value="cash">À vista (na data do documento)</option><option value="installments">Parcelado</option><option value="entry">Entrada + parcelas</option></select></label>@if (form.controls.payment_type.value !== 'cash') { <label>Parcelas<input type="number" min="1" max="36" formControlName="installment_count" /></label><label>1º vencimento (dias)<input type="number" min="0" max="3650" formControlName="first_due_days" /></label><label>Intervalo (dias)<input type="number" min="1" max="3650" formControlName="interval_days" /></label> }</div><div class="section-heading"><div><p class="eyebrow">Estoque opcional</p><h3>Materiais controlados no almoxarifado</h3></div><button type="button" class="secondary small" (click)="addLine()">+ Adicionar material</button></div><p class="purchase-flow-hint">Inclua somente materiais que deseja controlar no estoque. O saldo só muda quando o recebimento for confirmado.</p><div formArrayName="items" class="purchase-line-list">@for (line of lines.controls; track $index; let i = $index) { <div class="purchase-line-form expense-line" [formGroupName]="i"><label>Produto existente<select formControlName="product_id" (change)="selectProduct(i, $any($event.target).value)"><option value="">Vincular no recebimento</option>@for (product of availableProducts('warehouse'); track product.id) { <option [value]="product.id">{{ product.sku }} · {{ product.name }}</option> }</select></label><label>SKU<input formControlName="sku" placeholder="SKU do material" /></label><label class="line-description">Material / descrição<input formControlName="description" placeholder="Ex.: Fita crepe" /></label><label>Unidade<input formControlName="unit" placeholder="un, cx, rolo…" /></label><label>Quantidade<input type="number" min="0.001" step="0.001" formControlName="quantity" /></label><label class="money-field">Custo unitário (R$)<input appMoneyInput formControlName="unit_cost" min="0" inputmode="decimal" /></label>@if (lines.length > 1) { <button type="button" class="remove-line" aria-label="Remover material" (click)="removeLine(i)">×</button> }</div> }</div></div> } @else { <div class="purchase-form-section"><div class="section-heading"><div><p class="eyebrow">Lista de compra</p><h3>Peças em negociação</h3></div><button type="button" class="secondary small" (click)="addLine()">+ Adicionar peça</button></div>
            <p class="purchase-flow-hint">Nesta etapa, informe somente as peças e quantidades. Preços, frete, impostos e descontos entram em cada cotação de fornecedor.</p><div formArrayName="items" class="purchase-line-list">@for (line of lines.controls; track $index; let i = $index) { <div class="purchase-line-form" [formGroupName]="i"><label>Produto cadastrado<select formControlName="product_id" (change)="selectProduct(i, $any($event.target).value)"><option value="">Cadastrar/vincular depois</option>@for (product of availableProducts('product'); track product.id) { <option [value]="product.id">{{ product.sku }} · {{ product.name }}</option> }</select></label><label>SKU<input formControlName="sku" placeholder="Ex.: LR174890" /></label><label class="line-description">Peça / descrição<input formControlName="description" placeholder="Nome da peça" /></label><label>Quantidade<input type="number" min="0.001" step="0.001" formControlName="quantity" /></label>@if (lines.length > 1) { <button type="button" class="remove-line" aria-label="Remover peça" (click)="removeLine(i)">×</button> }</div> }</div>
          </div> }
          <label class="attachment-picker">Documentos <input type="file" multiple accept=".pdf,.xml,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx" (change)="setAttachments($any($event.target).files)" /><small>{{ selectedFiles().length ? selectedFiles().length + ' arquivo(s) selecionado(s)' : 'Nota fiscal, recibo, boleto ou comprovante (até 10 arquivos)' }}</small></label>
          @if (error()) { <p class="purchase-error" role="alert">{{ error() }}</p> }
          <div class="purchase-form-actions"><span class="muted">{{ form.controls.purchase_type.value === 'expense' ? 'Itens físicos só alteram o estoque após o recebimento' : lines.length + (lines.length === 1 ? ' peça' : ' peças') + ' · estoque só muda no recebimento' }}</span><button class="primary" [disabled]="saving() || (form.controls.purchase_type.value === 'parts' && form.invalid) || (form.controls.purchase_type.value === 'expense' && (!form.controls.expense_category.value || form.controls.expense_amount.value === null || lines.controls.some((line) => line.value.description && line.invalid)))">{{ saving() ? 'Salvando…' : 'Salvar compra' }}</button></div>
        </form>
      </section></div>
    }

    @if (detail(); as purchase) {
      <div class="modal-backdrop" (click)="detail.set(null)"><section class="modal wide purchase-modal purchase-detail" [class.restricted-costs]="!canReadCosts()" [class.read-only-purchases]="!canManagePurchases()" [class.no-receiving]="!canAdjustStock()" [class.costs-pending]="purchase.purchase_type === 'parts' && !purchase.selected_quote_id && !purchase.notes?.startsWith('Importação de documento.')" role="dialog" aria-modal="true" [attr.aria-label]="'Compra ' + purchase.number" (click)="$event.stopPropagation()">
        <div class="modal-head"><div><p class="eyebrow">Suprimentos · {{ purchase.number }}</p><h2>{{ purchase.number }}</h2>@if (purchase.supplier_order_number || purchase.document_date) { <p class="modal-intro">Pedido do fornecedor {{ purchase.supplier_order_number || '—' }}@if (purchase.document_date) { · documento de {{ dateOnly(purchase.document_date) }} }</p> }<p class="modal-intro">Criada em {{ purchase.created_at | date:'dd/MM/yyyy HH:mm' }} @if (purchase.needed_by) { · Previsão {{ dateOnly(purchase.needed_by) }} } @if (isOverdue(purchase)) { <strong class="overdue-chip">previsão vencida</strong> }</p></div><div class="detail-head-actions"><span class="purchase-badge" [attr.data-status]="purchase.status">{{ purchaseStatusLabel(purchase) }}</span>@if (canManagePurchases() && (purchase.status === 'negotiating' || purchase.status === 'approved')) { <button type="button" class="secondary small" [disabled]="saving()" (click)="draftEditor() ? closeDraftEditor() : openDraftEditor()">{{ draftEditor() ? 'Fechar edição' : 'Editar dados' }}</button> }@if (canManagePurchases()) { <button type="button" class="secondary small" (click)="copyPurchase(purchase)">Copiar compra</button> }<button class="close" aria-label="Fechar" (click)="detail.set(null)">×</button></div></div>
        @if (purchase.purchase_type === 'parts') { <div class="purchase-steps" aria-label="Etapas da compra">@for (step of workflow; track step.value; let i = $index) { <div class="purchase-step" [class.step-done]="stepIndex(purchase.status) > i" [class.step-current]="stepIndex(purchase.status) === i"><span>{{ stepIndex(purchase.status) > i ? '✓' : i + 1 }}</span><small>{{ step.label }}</small></div> }</div> } @else { <div class="expense-banner"><strong>Despesa da empresa</strong><span>{{ purchase.expense_category }} · {{ purchase.expense_amount | currency:'BRL' }}</span></div> }
        <div class="purchase-detail-grid">
          <div class="purchase-detail-main">
            @if (draftEditor() && canManagePurchases() && (purchase.status === 'negotiating' || purchase.status === 'approved')) { <section class="purchase-form-section draft-editor">
              <div class="section-heading"><div><p class="eyebrow">Rascunho</p><h3>Dados do pedido</h3></div><button type="button" class="secondary small" [disabled]="saving()" (click)="saveDraftHeader(purchase)">Salvar dados</button></div>
              <div class="purchase-form-meta">
                <label>Fornecedor<input type="text" list="supplierOptionsDetail" [value]="draftHeader().supplier_name" (input)="setDraftHeader('supplier_name', $any($event.target).value)" placeholder="Nome da empresa ou pessoa" /><datalist id="supplierOptionsDetail">@for (supplier of suppliers(); track supplier.id) { <option [value]="supplier.name"></option> }</datalist></label>
                <label>Previsão desejada<input type="date" [value]="draftHeader().needed_by" (input)="setDraftHeader('needed_by', $any($event.target).value)" /></label>
                <label>Nº do pedido do fornecedor<input type="text" [value]="draftHeader().supplier_order_number" (input)="setDraftHeader('supplier_order_number', $any($event.target).value)" placeholder="Opcional" /></label>
                <label>Data do documento<input type="date" [value]="draftHeader().document_date" (input)="setDraftHeader('document_date', $any($event.target).value)" /></label>
                <label class="notes-field">Observações<textarea rows="2" [value]="draftHeader().notes" (input)="setDraftHeader('notes', $any($event.target).value)"></textarea></label>
              </div>
              <div class="section-heading"><div><p class="eyebrow">Peças da negociação</p><h3>Editar linhas</h3></div></div>
              <div class="draft-lines">
                @for (item of purchase.items; track item.id) { <div class="draft-line">
                  <label>Descrição<input type="text" [value]="lineDrafts()[item.id]?.description ?? item.description" (input)="setLineDraft(item.id, 'description', $any($event.target).value)" /></label>
                  <label>SKU<input type="text" [value]="lineDrafts()[item.id]?.sku ?? item.sku" (input)="setLineDraft(item.id, 'sku', $any($event.target).value)" placeholder="Opcional no rascunho" /></label>
                  <label>Unidade<input type="text" [value]="lineDrafts()[item.id]?.unit ?? item.unit" (input)="setLineDraft(item.id, 'unit', $any($event.target).value)" /></label>
                  <label>Quantidade<input type="number" min="0.001" step="0.001" [value]="lineDrafts()[item.id]?.quantity ?? item.quantity" (input)="setLineDraft(item.id, 'quantity', $any($event.target).value)" /></label>
                  <div class="draft-line-actions"><button type="button" class="secondary small" [disabled]="saving()" (click)="saveLine(purchase, item)">Salvar peça</button>@if (purchase.status === 'negotiating' && purchase.items.length > 1) { <button type="button" class="danger-outline" [disabled]="saving()" (click)="removePurchaseLine(purchase, item)">Remover</button> }</div>
                </div> }
                @if (purchase.status === 'negotiating') { <div class="draft-line draft-line-new">
                  <label>Descrição<input type="text" [value]="newLineDraft().description" (input)="setNewLineDraft('description', $any($event.target).value)" placeholder="Nova peça" /></label>
                  <label>SKU<input type="text" [value]="newLineDraft().sku" (input)="setNewLineDraft('sku', $any($event.target).value)" placeholder="Opcional no rascunho" /></label>
                  <label>Unidade<input type="text" [value]="newLineDraft().unit" (input)="setNewLineDraft('unit', $any($event.target).value)" /></label>
                  <label>Quantidade<input type="number" min="0.001" step="0.001" [value]="newLineDraft().quantity" (input)="setNewLineDraft('quantity', $any($event.target).value)" /></label>
                  <div class="draft-line-actions"><button type="button" class="primary small" [disabled]="saving() || !newLineDraft().description.trim()" (click)="addDraftLine(purchase)">+ Adicionar peça</button></div>
                </div> }
              </div>
            </section> }
            @if (purchase.items.length) { <section class="purchase-form-section"><div class="section-heading"><div><p class="eyebrow">Itens e recebimento</p><h3>{{ purchase.purchase_type === 'expense' ? 'Materiais da despesa' : 'Peças da compra' }}</h3></div></div><div class="purchase-item-cards">@for (item of purchase.items; track item.id) { <article class="purchase-item-card"><div class="item-title"><div><strong>{{ item.description }}</strong><small><code>{{ item.sku }}</code>@if (item.product_id) { · vinculada ao catálogo } @else { · ainda sem produto no catálogo }</small></div><strong>{{ item.unit_cost | currency:'BRL' }} <small>/ {{ item.unit }} final</small></strong></div><div class="item-cost-breakdown"><span>Base: {{ item.base_unit_cost | currency:'BRL' }}</span><span>Frete: {{ item.freight_amount | currency:'BRL' }}</span><span>Impostos: {{ item.tax_amount | currency:'BRL' }}</span><span>Desconto: -{{ item.discount_amount | currency:'BRL' }}</span></div><div class="receipt-progress"><span>Recebido <b>{{ item.received_quantity | number:'1.0-3' }} / {{ item.quantity | number:'1.0-3' }} {{ item.unit }} · {{ item.quantity - item.received_quantity | number:'1.0-3' }} pendente</b></span><div><i [style.width.%]="progress(item)"></i></div></div>@if (purchase.status === 'ordered' || purchase.status === 'partially_received') { <div class="receive-controls"><label>Receber agora<input type="number" min="0.001" [max]="item.quantity - item.received_quantity" step="0.001" [value]="receiveQty(item)" (input)="setReceiveQty(item, $any($event.target).value)" /></label>@if (!item.product_id) { <label class="map-product">Vincular produto existente<select [value]="receiveProduct(item)" (change)="setReceiveProduct(item, $any($event.target).value)"><option value="">Selecione um produto…</option>@for (product of availableProducts(purchase.purchase_type === 'expense' ? 'warehouse' : 'product'); track product.id) { <option [value]="product.id">{{ product.sku }} · {{ product.name }}</option> }</select></label><label class="create-product-check"><input type="checkbox" [checked]="createNewProduct(item)" (change)="setCreateNewProduct(item, $any($event.target).checked)" /> Criar produto no catálogo ao receber</label> }<label class="receipt-note">Observação (avaria/divergência)<input type="text" maxlength="160" [value]="receiveObservation(item)" (input)="setReceiveObservation(item, $any($event.target).value)" placeholder="Opcional" /></label><button type="button" class="secondary small" [disabled]="saving() || receiveQty(item) <= 0" (click)="receive(item)">Registrar recebimento</button></div> }</article> }</div></section> }
            @if (purchase.purchase_type === 'parts' && (purchase.status === 'negotiating' || purchase.status === 'approved')) { <section class="purchase-form-section"><div class="section-heading"><div><p class="eyebrow">Concorrência</p><h3>Cotações de fornecedores</h3></div></div>@if (purchase.selected_quote_id) { <p class="muted">A cotação escolhida está travada. Registre uma nova proposta e escolha de novo para trocar preço ou prazo.</p> }@if (purchase.quotes.length) { <div class="quote-cards">@for (quote of purchase.quotes; track quote.id) { <article class="quote-card" [class.quote-selected]="purchase.selected_quote_id === quote.id"><div><strong>{{ quote.supplier_name }}</strong><b>{{ quote.total | currency:'BRL' }}</b></div><p>{{ quote.delivery_days !== null ? quote.delivery_days + ' dias para entrega' : 'Prazo não informado' }} @if (quote.payment_terms) { · {{ quote.payment_terms }} }</p><div class="quote-cost-summary">@for (item of purchase.items; track item.id) { <small>{{ item.sku }} · {{ quote.item_costs?.[item.id] | currency:'BRL' }}/un.</small> }</div><small>Condição: {{ quoteConditionLabel(quote) }}</small>@if (quote.notes) { <small>{{ quote.notes }}</small> }@if (purchase.selected_quote_id === quote.id) { <small class="quote-locked">Cotação escolhida · valores travados</small> } @else { <button type="button" class="secondary small" (click)="selectQuote(quote.id)">Escolher esta cotação</button> }</article> }</div> } @else { <p class="muted">Registre as propostas recebidas para comparar preço e prazo.</p> }
              <form class="quote-form" [formGroup]="quoteForm" (ngSubmit)="addQuote()"><div class="quote-item-costs"><strong>Custo unitário dos itens</strong>@for (item of purchase.items; track item.id) { <label class="money-field">Custo unitário (R$) &#183; {{ item.sku }} &#183; {{ item.description }}<input appMoneyInput [appMoneyInput]="quoteUnitCost(item)" min="0" (moneyInput)="setQuoteUnitCost(item, $event)" (moneyValidity)="setQuoteCostValidity(item.id, $event)" /></label> }</div><label>Fornecedor<input formControlName="supplier_name" placeholder="Nome do fornecedor" /></label><label>Contato<input formControlName="supplier_contact" placeholder="Telefone ou e-mail" /></label><label>Frete<input appMoneyInput formControlName="freight_amount" min="0" /></label><label>Impostos<input appMoneyInput formControlName="tax_amount" min="0" /></label><label>Desconto<input appMoneyInput formControlName="discount_amount" min="0" /></label><label>Ratear acréscimos/desconto<select formControlName="allocation_method"><option value="proportional">Proporcional ao subtotal de cada item</option><option value="quantity">Por quantidade de peças</option></select></label><label>Total final da proposta<input appMoneyInput [appMoneyInput]="quoteTotal(purchase)" min="0" (moneyInput)="setQuoteTotal($event)" /></label><label>Prazo (dias)<input type="number" min="0" formControlName="delivery_days" /></label><label>Condição de pagamento<select [value]="quoteForm.controls.payment_type.value" (change)="setQuoteConditionType($any($event.target).value)"><option value="cash">À vista</option><option value="installments">Parcelado</option><option value="entry">Entrada + parcelas</option></select></label>@if (quoteForm.controls.payment_type.value !== 'cash') { <label>Parcelas<input type="number" min="1" max="36" [value]="quoteForm.controls.installment_count.value" (input)="setQuoteConditionNumber('installment_count', $any($event.target).value)" /></label><label>1º vencimento (dias)<input type="number" min="0" max="3650" [value]="quoteForm.controls.first_due_days.value" (input)="setQuoteConditionNumber('first_due_days', $any($event.target).value)" /></label><label>Intervalo (dias)<input type="number" min="1" max="3650" [value]="quoteForm.controls.interval_days.value" (input)="setQuoteConditionNumber('interval_days', $any($event.target).value)" /></label> }<div class="quote-presets"><span>Atalhos</span><button type="button" class="secondary small" (click)="applyQuoteConditionPreset('cash')">À vista</button><button type="button" class="secondary small" (click)="applyQuoteConditionPreset('30')">30 dias</button><button type="button" class="secondary small" (click)="applyQuoteConditionPreset('30/60')">30/60</button><button type="button" class="secondary small" (click)="applyQuoteConditionPreset('30/60/90')">30/60/90</button></div><label class="quote-notes">Observação da condição<input formControlName="payment_terms" placeholder="Ex.: boleto combinado com o fornecedor" /></label><small class="quote-cost-hint">Parcelas do título: {{ quoteConditionPreview() }}</small><label class="quote-notes">Observações<input formControlName="notes" placeholder="Validade ou detalhes da proposta…" /></label><small class="quote-cost-hint">Custo considerado: {{ quoteTotal(purchase) | currency:'BRL' }} · {{ quoteDirectionNote() }}</small>@if (quoteRounding() !== 0) { <small class="quote-cost-hint">Ajuste de centavos de {{ quoteRounding() | currency:'BRL' }} aplicado no maior item para fechar o total.</small> }@if (quoteNet(purchase) < 0) { <p class="purchase-error" role="alert">O total da proposta é menor que o frete e os impostos menos o desconto.</p> }@if (quoteMismatch(purchase)) { <p class="purchase-error" role="alert">A soma dos itens não fecha com o total da proposta. Revise o rateio ou os valores.</p> }<button class="primary" [disabled]="quoteForm.invalid || quoteCostHasErrors() || !quoteCostsComplete(purchase) || quoteNet(purchase) < 0 || quoteMismatch(purchase) || saving()">Registrar cotação</button></form>
            </section> }
            @if (purchase.status === 'approved' && canManagePurchases()) { <div class="workflow-action"><div><strong>Cotação aprovada</strong><span>A compra ainda não altera o estoque.</span></div><button class="primary" [disabled]="saving()" (click)="placeOrder()">Registrar pedido ao fornecedor</button></div> }
            @if (purchase.notes) { <section class="purchase-notes"><span class="eyebrow">Observações internas</span><p>{{ purchase.notes }}</p></section> }
            <section class="purchase-form-section"><div class="section-heading"><div><p class="eyebrow">Documentação</p><h3>Documentos anexados</h3></div>@if (canManagePurchases()) { <label class="attachment-inline">+ Anexar documentos<input type="file" multiple (change)="uploadAttachments(purchase, $any($event.target).files)" /></label> }</div>@if (purchase.attachments.length) { <div class="attachment-list">@for (attachment of purchase.attachments; track attachment.id) { <button type="button" class="attachment-row" (click)="downloadAttachment(purchase, attachment)"><span>📎 {{ attachment.filename }}</span><small>{{ formatBytes(attachment.size_bytes) }}</small></button> }</div> } @else { <p class="muted">Nenhum documento anexado ainda.</p> }</section>
          </div>
          <aside class="purchase-aside"><section class="purchase-aside-card"><p class="eyebrow">Resumo</p><div><span>Itens</span><strong>{{ purchase.items.length }}</strong></div>@if (purchase.purchase_type === 'parts') { <div><span>Unidades pedidas</span><strong>{{ totalUnits(purchase) | number:'1.0-3' }}</strong></div><div><span>Recebidas</span><strong>{{ receivedUnits(purchase) | number:'1.0-3' }}</strong></div> }@if (selectedQuote(purchase); as quote) { <div><span>Fornecedor escolhido</span><strong>{{ quote.supplier_name }}</strong></div><div><span>Valor acordado</span><strong>{{ quote.total | currency:'BRL' }}</strong></div> }</section>
            @if (purchase.payables?.length) { <section class="purchase-aside-card payable-card"><p class="eyebrow">Contas a pagar</p>@for (payable of purchase.payables; track payable.id) { <div class="payable-row"><div><strong>{{ payable.amount | currency:'BRL' }}</strong><small>{{ payableLabel(payable) }}</small>@if (payable.payment_terms) { <small>Condição {{ payable.payment_terms }}</small> }@if (payable.installments?.length) { <div class="payable-installments">@for (installment of payable.installments; track installment.id) { <small>{{ installment.number }}ª · {{ dateOnly(installment.due_date) }} · {{ installment.amount | currency:'BRL' }}@if ((installment.paid_amount ?? 0) > 0) { · pago {{ installment.paid_amount | currency:'BRL' }} }</small> }</div> }@if ((payable.paid_amount ?? 0) > 0) { <small>Pago {{ payable.paid_amount | currency:'BRL' }} · saldo {{ payable.amount - (payable.paid_amount ?? 0) | currency:'BRL' }}</small> }</div>@if (canManagePurchases() && (payable.status === 'open' || payable.status === 'partial')) { <button type="button" class="secondary small" [disabled]="saving()" (click)="settlePayable(purchase, payable)">Registrar pagamento</button> }</div> }</section> }
            <section class="purchase-aside-card timeline-card"><p class="eyebrow">Histórico da compra</p>@for (event of purchase.events; track event.id) { <div class="purchase-event"><i></i><div><strong>{{ event.detail }}</strong><small>{{ event.created_at | date:'dd/MM/yyyy HH:mm' }}</small></div></div> }</section>
            @if (purchaseStatusNote(purchase); as note) { <p class="purchase-status-note">{{ note }}</p> }
            @if (canManagePurchases() && isActive(purchase)) { <div class="purchase-lifecycle-actions">
              @if (purchase.status === 'ordered' || purchase.status === 'partially_received') { <button type="button" class="secondary" [disabled]="saving()" (click)="receiveAll(purchase)">Receber tudo</button> }
              @if (purchase.status === 'ordered' || purchase.status === 'partially_received') { <button type="button" class="secondary" [disabled]="saving()" (click)="openLifecycleForm('close')">Encerrar saldo</button> }
              <button type="button" class="cancel-purchase" [disabled]="saving()" (click)="openLifecycleForm('cancel')">Cancelar compra</button>
              <button type="button" class="danger-outline" [disabled]="saving()" (click)="requestDelete(purchase)">Excluir compra</button>
            </div> }
            @if (lifecycleForm(); as form) { <section class="purchase-aside-card lifecycle-form">
              <p class="eyebrow">{{ form.mode === 'cancel' ? 'Cancelar compra' : 'Encerrar saldo pendente' }}</p>
              <label>Motivo<input type="text" maxlength="255" [value]="form.reason" (input)="setLifecycleReason($any($event.target).value)" placeholder="Ex.: fornecedor não entregou o restante" /></label>
              @if (form.mode === 'cancel' && hasReceived(purchase)) { <fieldset class="lifecycle-resolution"><legend>O que fazer com o material já recebido?</legend>
                <label><input type="radio" name="resolution" [checked]="form.resolution === 'keep_received'" (change)="setLifecycleResolution('keep_received')" /> Manter o recebido e encerrar o saldo</label>
                <label><input type="radio" name="resolution" [checked]="form.resolution === 'return_received'" (change)="setLifecycleResolution('return_received')" /> Registrar devolução ao fornecedor (saída de estoque)</label>
              </fieldset> }
              <div class="lifecycle-actions"><button type="button" class="secondary small" (click)="lifecycleForm.set(null)">Voltar</button><button type="button" class="primary small" [disabled]="saving() || form.reason.trim().length < 3" (click)="submitLifecycle(purchase)">Confirmar</button></div>
            </section> }
          </aside>
        </div>
        @if (error()) { <p class="purchase-error" role="alert">{{ error() }}</p> }
      </section></div>
    }
  `,
  styleUrl: './purchases.scss',
  host: { '(document:click)': 'closeRowMenu()', '(window:scroll)': 'closeRowMenu()' },
})
export class PurchasesPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly live = inject(LiveUpdatesService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  readonly purchases = signal<Purchase[]>([]);
  canManagePurchases() { return canManagePurchases(this.auth.user()?.role); }
  canManageCatalog() { return canManageCatalog(this.auth.user()?.role); }
  canAdjustStock() { return canAdjustStock(this.auth.user()?.role); }
  canReadCosts() { return canReadCosts(this.auth.user()?.role); }
  readonly products = signal<Product[]>([]);
  readonly suppliers = signal<Array<{ id: string; name: string; contact: string | null; default_delivery_days: number | null; default_payment_terms: string | null }>>([]);
  readonly detail = signal<Purchase | null>(null);
  readonly page = signal(1);
  readonly pageSize = 25;
  readonly selectedIds = signal<Record<string, boolean>>({});
  readonly draftEditor = signal(false);
  readonly draftHeader = signal({ supplier_name: '', supplier_order_number: '', document_date: '', needed_by: '', notes: '' });
  readonly lineDrafts = signal<Record<string, { description: string; sku: string; unit: string; quantity: number }>>({});
  readonly newLineDraft = signal({ description: '', sku: '', unit: 'un', quantity: 1 });
  readonly rowMenuId = signal<string | null>(null);
  readonly rowMenuPosition = signal<{ top: number; left: number } | null>(null);
  readonly showNew = signal(false);
  readonly saving = signal(false);
  readonly error = signal('');
  readonly message = signal('');
  readonly search = signal('');
  readonly statusFilter = signal('all');
  readonly receiveValues = signal<Record<string, { quantity: number; productId: string; create: boolean }>>({});
  readonly receiptIds = signal<Record<string, string>>({});
  readonly receiveObservations = signal<Record<string, string>>({});
  readonly quoteCosts = signal<Record<string, number>>({});
  readonly quoteCostValidity = signal<Record<string, boolean>>({});
  readonly quoteTotalValue = signal<number | null>(null);
  readonly quoteRounding = signal(0);
  readonly lifecycleForm = signal<{ mode: 'cancel' | 'close'; reason: string; resolution: 'keep_received' | 'return_received' } | null>(null);
  readonly deleteTarget = signal<Purchase | null>(null);
  readonly deleteReason = signal('');
  readonly importMoneyValidity = signal<Record<string, boolean>>({});
  readonly importProductSearch = signal<Record<number, string>>({});
  readonly importProductResults = signal<Record<number, Product[]>>({});
  private readonly importSearchRevision = signal<Record<number, number>>({});
  readonly importProductModal = signal(false);
  readonly importProductLine = signal<number | null>(null);
  readonly savingImportProduct = signal(false);
  readonly importProductError = signal('');
  readonly importProductDraft = signal({ sku: '', stock_type: 'product' as 'product' | 'warehouse', name: '', description: '', sale_price: 0, cost_price: 0, minimum_stock: 0, brand: '', manufacturer: '', manufacturer_part_number: '', barcode: '', category: '', item_condition: 'new' as 'new' | 'used' | 'refurbished', warranty_days: null as number | null, origin_country: '', weight_g: null as number | null, package_length_cm: null as number | null, package_width_cm: null as number | null, package_height_cm: null as number | null });
  private readonly importId = signal<string | null>(null);
  readonly selectedFiles = signal<File[]>([]);
  readonly importReview = signal<any | null>(null);
  readonly importProfiles = signal<Array<{ profile_id: string; name: string; kind: string; version: number }>>([]);
  readonly importDraft = signal<{ supplier: string; orderNumber: string; documentDate: string; total: number | null; shipping: number | null; discount: number | null; tax: number | null; currency: string | null; exchangeRate: number | null; paidAmount: number | null; items: Array<{ description: string; sku: string; quantity: number; unit_cost: number; confidence: number; product_id: string | null; stock_controlled: boolean; line_total: number; discount_amount: number; source: string; quantityDerived: boolean }> }>({ supplier: '', orderNumber: '', documentDate: '', total: null, shipping: null, discount: null, tax: null, currency: null, exchangeRate: null, paidAmount: null, items: [] });
  readonly importDuplicate = signal<{ purchase_id: string; purchase_number: string; purchase_status: string; cancelled: boolean } | null>(null);
  readonly importCheck = signal<{ items_total: number | null; closing_difference: number | null; subtotal_difference: number | null; balanced: boolean } | null>(null);
  readonly importType = signal<'parts' | 'expense'>('parts');
  readonly importCategory = signal('');
  readonly importPaidNow = signal(false);
  readonly importPaidDate = signal('');
  readonly importPaidMethod = signal('');
  readonly importFile = signal<File | null>(null);
  readonly importLoading = signal(false);
  readonly creatingImport = signal(false);
  readonly importError = signal('');
  readonly expenseCategories = ['Aluguel', 'Energia e água', 'Internet e telefonia', 'Contabilidade', 'Marketing', 'Frete e transporte', 'Material de escritório', 'Materiais de consumo e embalagem', 'Impostos e taxas', 'Serviços', 'Outros'];
  private readonly initialRange = quickDateRange('last30');
  readonly startDate = signal(this.initialRange.startDate);
  readonly endDate = signal(this.initialRange.endDate);
  readonly statuses: { value: string; label: string }[] = [
    { value: 'negotiating', label: 'Em negociação' }, { value: 'approved', label: 'Aprovada' },
    { value: 'ordered', label: 'Pedido enviado' }, { value: 'partially_received', label: 'Recebimento parcial' },
    { value: 'received', label: 'Recebida' }, { value: 'closed', label: 'Encerrada' },
    { value: 'cancelled', label: 'Cancelada' },
  ];
  readonly workflow = [{ value: 'negotiating', label: 'Negociação' }, { value: 'approved', label: 'Aprovação' }, { value: 'ordered', label: 'Pedido' }, { value: 'received', label: 'Recebimento' }];
  readonly form = this.fb.group({
    purchase_type: ['parts'], supplier_name: [''], supplier_order_number: [''], document_date: [''], expense_category: [''], expense_amount: [0, [Validators.min(0)]], needed_by: [''], notes: [''], payment_type: ['cash' as PaymentConditionType], installment_count: [1, [Validators.min(1), Validators.max(36)]], first_due_days: [0, [Validators.min(0)]], interval_days: [30, [Validators.min(1)]], items: this.fb.array([this.newLine()]),
  });
  readonly quoteForm = this.fb.nonNullable.group({ supplier_name: ['', Validators.required], supplier_contact: [''], freight_amount: [0, [Validators.required, Validators.min(0)]], tax_amount: [0, [Validators.required, Validators.min(0)]], discount_amount: [0, [Validators.required, Validators.min(0)]], allocation_method: ['proportional' as 'proportional' | 'quantity'], delivery_days: [null as number | null], payment_type: ['cash' as PaymentConditionType], installment_count: [1, [Validators.min(1), Validators.max(36)]], first_due_days: [30, [Validators.min(0)]], interval_days: [30, [Validators.min(1)]], payment_terms: [''], notes: [''] });
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
    { status: 'ordered', label: 'Aguardando recebimento', count: this.periodPurchases().filter((p) => ['ordered', 'partially_received'].includes(p.status)).length, note: 'Peças e materiais pendentes' },
    { status: 'received', label: 'Concluídas', count: this.periodPurchases().filter((p) => p.status === 'received').length, note: 'Compras recebidas ou despesas lançadas' },
  ]);

  private purchaseLocalDate(purchase: Purchase) {
    const date = new Date(purchase.created_at);
    return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
  }

  ngOnInit() { this.load(); this.refreshProducts(); this.loadSuppliers(); this.api.purchaseImportProfiles().subscribe({ next: (result) => this.importProfiles.set(result.profiles), error: () => undefined }); this.live.changes$.pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef)).subscribe(() => { this.load(); this.refreshProducts(); this.loadSuppliers(); }); this.quoteForm.valueChanges.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(() => { const purchase = this.detail(); const typed = this.quoteTotalValue(); if (purchase && typed !== null) this.distributeQuoteTotal(purchase, typed); }); }
  private refreshProducts() { this.api.products('', false).subscribe({ next: (items) => this.products.set(items), error: () => undefined }); }
  private loadSuppliers() { this.api.suppliers().subscribe({ next: (items) => this.suppliers.set(items), error: () => undefined }); }
  onImportDocument(event: Event) {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0]; input.value = '';
    if (!file) return;
    this.importFile.set(file); this.importError.set(''); this.importLoading.set(true);
    this.api.analyzePurchaseDocument(file).pipe(finalize(() => this.importLoading.set(false))).subscribe({
      next: (review) => this.applyImportReview(review),
      error: (err) => { const message = err?.error?.detail || 'Não foi possível analisar o documento. A compra manual continua disponível.'; this.importError.set(message); this.error.set(message); },
    });
  }
  private applyImportReview(review: any) {
    this.importMoneyValidity.set({});
    this.importId.set(crypto.randomUUID());
    this.importProductSearch.set({}); this.importProductResults.set({}); this.importSearchRevision.set({});
    this.importReview.set(review);
    this.importDraft.set({
      supplier: String(review.fields?.supplier?.value || ''),
      orderNumber: String(review.fields?.order_number?.value || ''),
      documentDate: String(review.fields?.date?.value || ''),
      total: review.fields?.total?.value == null ? null : Number(review.fields.total.value),
      shipping: review.fields?.shipping?.value == null ? null : Number(review.fields.shipping.value),
      discount: review.fields?.discount?.value == null ? null : Number(review.fields.discount.value),
      tax: review.fields?.tax?.value == null ? null : Number(review.fields.tax.value),
      currency: review.currency ? String(review.currency) : null,
      exchangeRate: review.exchange_rate == null ? null : Number(review.exchange_rate),
      paidAmount: review.paid?.amount == null ? null : Number(review.paid.amount),
      items: (review.items || []).map((item: any) => {
        const sku = String(item.sku || '').trim();
        // Vínculo automático só com correspondência exata de SKU ou código de barras (P14).
        const match = sku
          ? this.products().find((product) => product.sku.toLowerCase() === sku.toLowerCase() || (!!product.barcode && product.barcode === sku))
          : undefined;
        return {
          description: String(item.description || ''), sku, product_id: match ? match.id : null, stock_controlled: true,
          quantity: Number(item.quantity ?? 0), unit_cost: Number(item.unit_cost ?? 0), line_total: Number(item.line_total ?? Number(item.quantity ?? 0) * Number(item.unit_cost ?? 0)), discount_amount: Number(item.discount_amount ?? 0),
          confidence: Number(item.confidence ?? 0), source: String(item.source || ''), quantityDerived: !!item.quantity_derived,
        };
      }),
    });
    this.importError.set('');
    this.importCheck.set(review.check || null);
    this.checkImportDuplicate();
  }
  private checkImportDuplicate() {
    const review = this.importReview();
    const number = String(review?.fields?.order_number?.value || '').trim();
    const origin = String(review?.profile?.profile_id || '').trim();
    this.importDuplicate.set(null);
    if (!number || !origin) return;
    this.api.purchaseImportDuplicates({ order_number: number, origin }).pipe(takeUntilDestroyed(this.destroyRef)).subscribe({
      next: (result) => this.importDuplicate.set(result.match),
      error: () => this.importDuplicate.set(null),
    });
  }
  changeImportProfile(profileId: string) {
    const file = this.importFile(); if (!file) return;
    this.importLoading.set(true);
    this.api.analyzePurchaseDocument(file, profileId || undefined).pipe(finalize(() => this.importLoading.set(false))).subscribe({
      next: (review) => this.applyImportReview(review),
      error: (err) => this.importError.set(err?.error?.detail || 'Não foi possível processar com este perfil.'),
    });
  }
  updateImportField(field: 'supplier' | 'orderNumber' | 'documentDate', value: string) { this.importDraft.update((draft) => ({ ...draft, [field]: value })); }
  setImportRate(value: number | null) { this.importDraft.update((draft) => ({ ...draft, exchangeRate: value })); }
  setImportRateFromInput(value: string) { this.setImportRate(value === '' ? null : Number(value)); }
  fieldOrigin(field: { source?: string; confidence?: number } | undefined): string {
    if (!field) return 'não identificado';
    const source = String(field.source || '');
    if (source === 'xml') return 'XML da NF-e';
    if (source === 'ocr') return `OCR · qualidade ${Math.round((Number(field.confidence) || 0) * 100)}%`;
    if (source === 'pdf_text') return 'texto do documento';
    if (source === 'columns') return 'grade do documento';
    return 'documento';
  }
  itemOrigin(item: { source?: string; confidence?: number; quantity_derived?: boolean; quantityDerived?: boolean }): string {
    const base = this.fieldOrigin(item);
    const derived = item.quantity_derived ?? item.quantityDerived;
    return derived ? `${base} · quantidade derivada` : base;
  }
  setImportPaid(value: number | null) { this.importDraft.update((draft) => ({ ...draft, paidAmount: value })); }
  importItemsTotal() { return this.importDraft().items.reduce((sum, item) => sum + Number(item.line_total || 0), 0); }
  importClosingDifference() {
    const check = this.importCheck();
    if (check) return check.closing_difference ?? 0;
    const draft = this.importDraft();
    if (draft.total === null || !draft.items.length) return 0;
    return Number((this.importItemsTotal() + Number(draft.shipping || 0) + Number(draft.tax || 0) - Number(draft.discount || 0) - Number(draft.total)).toFixed(2));
  }
  importHasItemsToCheck() { return !!this.importCheck()?.items_total || this.importDraft().items.length > 0; }
  importPaidDifference() {
    const draft = this.importDraft();
    if (draft.paidAmount === null || draft.total === null) return 0;
    return Number((Number(draft.paidAmount) - Number(draft.total)).toFixed(2));
  }
  importNeedsRate() {
    const currency = this.importDraft().currency;
    return !!currency && currency.toUpperCase() !== 'BRL';
  }
  updateImportNumber(field: 'total' | 'shipping' | 'discount' | 'tax', value: number | null) { this.importDraft.update((draft) => ({ ...draft, [field]: value })); }
  updateImportItem(index: number, field: 'description' | 'sku' | 'quantity' | 'unit_cost' | 'discount_amount', value: string | number | null) {
    this.importDraft.update((draft) => ({ ...draft, items: draft.items.map((item, i) => { if (i !== index) return item; const updated = { ...item, [field]: field === 'description' || field === 'sku' ? value : Number(value ?? 0) }; if (field === 'quantity' || field === 'unit_cost' || field === 'discount_amount') updated.line_total = Math.max(0, Number(updated.quantity) * Number(updated.unit_cost) - Number(updated.discount_amount)); return updated; }) }));
  }
  setImportMoneyValidity(key: string, invalid: boolean) { this.importMoneyValidity.update((values) => ({ ...values, [key]: invalid })); }
  searchImportProducts(index: number, value: string) { this.importProductSearch.update((rows) => ({ ...rows, [index]: value })); const revision = (this.importSearchRevision()[index] || 0) + 1; this.importSearchRevision.update((rows) => ({ ...rows, [index]: revision })); if (!value.trim()) { this.importProductResults.update((rows) => ({ ...rows, [index]: [] })); return; } this.api.products(value.trim(), false).subscribe({ next: (products) => { if (this.importSearchRevision()[index] === revision) this.importProductResults.update((rows) => ({ ...rows, [index]: products.filter((product) => product.stock_type === 'product' || product.stock_type === 'warehouse') })); }, error: () => { if (this.importSearchRevision()[index] === revision) this.importProductResults.update((rows) => ({ ...rows, [index]: [] })); } }); }
  selectedImportProduct(id: string | null) { return id ? this.products().find((product) => product.id === id) || Object.values(this.importProductResults()).flat().find((product) => product.id === id) || null : null; }
  selectImportedProduct(index: number, product: Product) { this.importDraft.update((draft) => ({ ...draft, items: draft.items.map((item, i) => i === index ? { ...item, product_id: product.id, stock_controlled: true, sku: item.sku || product.sku } : item) })); this.products.update((items) => items.some((entry) => entry.id === product.id) ? items : [...items, product]); this.importProductSearch.update((rows) => ({ ...rows, [index]: '' })); this.importProductResults.update((rows) => ({ ...rows, [index]: [] })); }
  setImportStockControlled(index: number, value: boolean) { this.importDraft.update((draft) => ({ ...draft, items: draft.items.map((item, i) => i === index ? { ...item, stock_controlled: value, product_id: value ? item.product_id : null } : item) })); }
  clearImportedProduct(index: number) { this.importDraft.update((draft) => ({ ...draft, items: draft.items.map((item, i) => i === index ? { ...item, product_id: null } : item) })); }
  openImportProductCreate(index: number) { const item = this.importDraft().items[index]; this.importProductLine.set(index); this.importProductError.set(''); this.importProductDraft.set({ sku: item.sku, stock_type: 'product', name: item.description, description: item.description, sale_price: 0, cost_price: 0, minimum_stock: 0, brand: '', manufacturer: '', manufacturer_part_number: '', barcode: '', category: '', item_condition: 'new', warranty_days: null, origin_country: '', weight_g: null, package_length_cm: null, package_width_cm: null, package_height_cm: null }); this.importProductModal.set(true); }
  closeImportProductCreate() { if (!this.savingImportProduct()) this.importProductModal.set(false); }
  updateImportProduct(field: string, value: string | number | null) { this.importProductDraft.update((draft) => { const numeric = ['sale_price', 'cost_price', 'minimum_stock', 'warranty_days', 'weight_g', 'package_length_cm', 'package_width_cm', 'package_height_cm'].includes(field); return { ...draft, [field]: numeric ? value === '' || value == null ? null : Number(value) : value } as typeof draft; }); }
  canSaveImportProduct() { const value = this.importProductDraft(); return value.sku.trim().length > 0 && value.sku.trim().length <= 80 && value.name.trim().length >= 2 && value.name.trim().length <= 200; }
  saveImportProduct() { if (!this.canSaveImportProduct() || this.savingImportProduct()) return; const index = this.importProductLine(), draft = this.importProductDraft(); if (index == null) return; this.savingImportProduct.set(true); this.importProductError.set(''); this.api.createProduct({ ...draft, sku: draft.sku.trim(), name: draft.name.trim(), current_stock: 0, sale_price: draft.sale_price ?? 0, cost_price: draft.cost_price ?? 0, minimum_stock: draft.minimum_stock ?? 0, attributes: {}, fitments: [] }).pipe(finalize(() => this.savingImportProduct.set(false))).subscribe({ next: (product) => { this.selectImportedProduct(index, product); this.importProductModal.set(false); }, error: (err) => this.importProductError.set(err?.error?.detail || 'Não foi possível cadastrar o produto. Confira SKU e campos obrigatórios.') }); }
  private importNotes(review: any, draft: { orderNumber: string; documentDate: string; total: number | null; shipping: number | null; discount: number | null; tax: number | null }): string {
    const metadata = [
      `Perfil: ${review.profile.name}`,
      draft.orderNumber ? `Pedido: ${draft.orderNumber}` : '',
      draft.documentDate ? `Data no documento: ${draft.documentDate}` : '',
      draft.shipping != null ? `Frete no documento: ${draft.shipping}` : '',
      draft.discount != null ? `Desconto no documento: ${draft.discount}` : '',
      draft.tax != null ? `Impostos no documento: ${draft.tax}` : '',
      `Total no documento: ${draft.total ?? 'não identificado'}`,
      'Documento revisado pelo usuário.',
    ].filter(Boolean);
    return `Importação de documento. ${metadata.join(' · ')}`.slice(0, 4000);
  }
  private allocateImportTotal(total: number | null, items: Array<{ quantity: number; unit_cost: number }>, index: number) {
    if (total == null || !Number.isFinite(total) || total <= 0) return 0;
    const weights = items.map((item) => Math.max(0, item.quantity * item.unit_cost));
    const weightSum = weights.reduce((sum, weight) => sum + weight, 0);
    if (!weightSum) return index === 0 ? Number(total.toFixed(2)) : 0;
    if (index === items.length - 1) {
      const allocated = weights.slice(0, index).reduce((sum, weight) => sum + Math.round(total * weight / weightSum * 100) / 100, 0);
      return Number((total - allocated).toFixed(2));
    }
    return Math.round(total * weights[index] / weightSum * 100) / 100;
  }
  canConfirmImport() {
    const items = this.importDraft().items;
    const duplicate = this.importDuplicate();
    if (duplicate && !duplicate.cancelled) return false;
    if (this.importNeedsRate() && !(Number(this.importDraft().exchangeRate) > 0)) return false;
    if (this.importType() === 'expense') {
      return this.importCategory().trim().length > 1 && Number(this.importDraft().total) > 0 && !Object.values(this.importMoneyValidity()).some(Boolean);
    }
    return !Object.values(this.importMoneyValidity()).some(Boolean) && items.length > 0 && items.every((item) => (!item.stock_controlled || !!item.product_id) && item.description.trim().length >= 2 && Number.isFinite(item.quantity) && item.quantity > 0 && Number.isFinite(item.unit_cost) && item.unit_cost >= 0 && Number.isFinite(item.discount_amount) && item.discount_amount >= 0 && item.discount_amount <= item.quantity * item.unit_cost);
  }
  setImportType(value: 'parts' | 'expense') {
    this.importType.set(value);
    if (value === 'expense' && !this.importCategory()) this.importCategory.set(this.expenseCategories[0]);
  }
  setImportPaidNow(value: boolean) {
    this.importPaidNow.set(value);
    if (value && !this.importPaidDate()) this.importPaidDate.set(this.today());
  }
  private today() {
    const now = new Date();
    return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  }
  useImportCandidate(candidate: { text: string; quantity?: number; unit_cost?: number }) {
    const quantity = Number(candidate.quantity ?? 1) || 1;
    const unitCost = Number(candidate.unit_cost ?? 0);
    this.importDraft.update((draft) => ({
      ...draft,
      items: [
        ...draft.items,
        {
          description: candidate.text,
          sku: '',
          quantity,
          unit_cost: unitCost,
          line_total: Number((quantity * unitCost).toFixed(2)),
          discount_amount: 0,
          confidence: 0,
          product_id: null,
          stock_controlled: true,
          source: 'candidato',
          quantityDerived: candidate.quantity === undefined,
        },
      ],
    }));
  }
  addImportLine() { this.importDraft.update((draft) => ({ ...draft, items: [...draft.items, { description: '', sku: '', quantity: 1, unit_cost: 0, confidence: 0, product_id: null, stock_controlled: true, line_total: 0, discount_amount: 0, source: '', quantityDerived: false }] })); }
  removeImportLine(index: number) { this.importDraft.update((draft) => ({ ...draft, items: draft.items.filter((_, i) => i !== index) })); this.importMoneyValidity.update((values) => Object.fromEntries(Object.entries(values).filter(([key]) => !key.startsWith('item-')))); }
  closeImportReview() { if (this.creatingImport()) return; this.importReview.set(null); this.importFile.set(null); this.importId.set(null); this.importError.set(''); this.importProductModal.set(false); }
  createImportedPurchase() {
    const review = this.importReview(), file = this.importFile(), draft = this.importDraft(), importId = this.importId();
    if (!review || !file || !importId || !this.canConfirmImport() || this.creatingImport()) return;
    this.creatingImport.set(true); this.importError.set('');
    const isExpense = this.importType() === 'expense';
    const payload = {
      purchase_type: this.importType(), source_import_id: importId, supplier_name: draft.supplier.trim() || null,
      expense_category: isExpense ? this.importCategory().trim() || null : null,
      expense_amount: isExpense ? draft.total : null,
      supplier_id: this.supplierByName(draft.supplier)?.id ?? null,
      supplier_order_number: draft.orderNumber.trim() || null,
      purchase_origin: review.profile?.profile_id || null,
      document_access_key: review.fields?.access_key?.value ?? null,
      document_number: review.fields?.document_number?.value ?? null,
      document_series: review.fields?.document_series?.value ?? null,
      issuer_cnpj: review.fields?.issuer_cnpj?.value ?? null,
      original_currency: draft.currency,
      original_total: draft.total,
      exchange_rate: draft.exchangeRate,
      paid_amount: draft.paidAmount,
      paid_now: this.importPaidNow(),
      paid_date: this.importPaidNow() ? this.importPaidDate() || null : null,
      paid_method: this.importPaidNow() ? this.importPaidMethod().trim() || null : null,
      document_date: draft.documentDate || null,
      notes: this.importNotes(review, draft),
      items: (isExpense ? draft.items.filter((item) => item.stock_controlled && item.product_id) : draft.items).map((item, index) => ({
        sku: item.sku.trim(), description: item.description.trim(), quantity: item.quantity,
        unit_cost: item.unit_cost, product_id: item.product_id,
        freight_amount: this.allocateImportTotal(draft.shipping, draft.items, index),
        tax_amount: this.allocateImportTotal(draft.tax, draft.items, index),
        discount_amount: item.discount_amount + this.allocateImportTotal(draft.discount, draft.items, index),
      })),
    };
    this.api.confirmImportedPurchase(file, payload).pipe(finalize(() => this.creatingImport.set(false))).subscribe({
      next: (purchase) => {
        this.importReview.set(null); this.importFile.set(null);
        this.purchases.update((list) => [purchase, ...list]);
        const alreadyAttached = purchase.attachments.some((attachment) => attachment.filename === file.name && attachment.size_bytes === file.size);
        if (!alreadyAttached) this.error.set('O documento não voltou anexado; confira o anexo na compra.');
        this.openDetails(purchase);
      },
      error: (err) => this.importError.set(this.importErrorText(err)),
    });
  }
  private importErrorText(err: any): string {
    const detail = err?.error?.detail;
    if (typeof detail === 'string') return detail;
    if (Array.isArray(detail)) return detail.map((entry) => entry?.msg || '').filter(Boolean).join(' · ') || 'Confira os campos da revisão.';
    if (detail?.message) return String(detail.message);
    return 'Não foi possível criar a compra revisada.';
  }

  private newLine() { return this.fb.group({ product_id: [''], sku: [''], description: ['', Validators.required], unit: ['un', Validators.required], quantity: [1, [Validators.required, Validators.min(0.001)]], unit_cost: [0, [Validators.required, Validators.min(0)]] }); }
  load() { this.api.purchases().subscribe({ next: (items) => this.purchases.set(items), error: () => this.error.set('Não foi possível carregar as compras. Tente novamente.') }); }
  applyPeriod(range: DateRange) { this.startDate.set(range.startDate); this.endDate.set(range.endDate); }
  toggleStatus(status: string) { this.statusFilter.set(this.statusFilter() === status ? 'all' : status); }
  openNew() { this.closeRowMenu(); this.error.set(''); this.selectedFiles.set([]); this.form.reset({ purchase_type: 'parts', supplier_name: '', expense_category: '', expense_amount: 0, needed_by: '', notes: '', payment_type: 'cash', installment_count: 1, first_due_days: 0, interval_days: 30 }); while (this.lines.length) this.lines.removeAt(0); this.addLine(); this.showNew.set(true); }
  toggleRowMenu(id: string, event: Event) {
    event.stopPropagation();
    if (this.rowMenuId() === id) { this.closeRowMenu(); return; }
    const trigger = event.currentTarget as HTMLElement;
    const rect = trigger.getBoundingClientRect();
    const menuWidth = 130;
    const menuHeight = 48;
    let top = rect.bottom + 4;
    if (top + menuHeight > window.innerHeight - 8) top = Math.max(8, rect.top - menuHeight - 4);
    const left = Math.max(8, Math.min(rect.right - menuWidth, window.innerWidth - menuWidth - 8));
    this.rowMenuPosition.set({ top, left });
    this.rowMenuId.set(id);
  }
  rowMenuPurchase() { return this.purchases().find((purchase) => purchase.id === this.rowMenuId()) ?? null; }
  closeRowMenu() { this.rowMenuId.set(null); this.rowMenuPosition.set(null); }
  copyPurchaseFromList(purchase: Purchase, event: Event) { event.stopPropagation(); this.copyPurchase(purchase); }
  copyPurchase(purchase: Purchase) {
    this.closeRowMenu();
    this.error.set('');
    this.selectedFiles.set([]);
    this.form.reset({
      purchase_type: purchase.purchase_type,
      supplier_name: purchase.supplier_name ?? '',
      expense_category: purchase.expense_category ?? '',
      expense_amount: purchase.expense_amount ?? 0,
      needed_by: '',
      notes: purchase.notes ? `Cópia de ${purchase.number}\n${purchase.notes}` : `Cópia de ${purchase.number}`,
    });
    while (this.lines.length) this.lines.removeAt(0);
    if (purchase.purchase_type === 'parts') {
      for (const item of purchase.items) {
        const line = this.newLine();
        line.patchValue({ product_id: item.product_id ?? '', sku: item.sku, description: item.description, quantity: item.quantity });
        this.lines.push(line);
      }
    } else {
      this.addLine();
    }
    this.detail.set(null);
    this.showNew.set(true);
  }
  addLine() { this.lines.push(this.newLine()); }
  removeLine(index: number) { this.lines.removeAt(index); }
  selectProduct(index: number, id: string) { const line = this.lines.at(index); const product = this.products().find((entry) => entry.id === id); if (product) line.patchValue({ product_id: id, sku: product.sku, description: product.name }); else line.patchValue({ product_id: '', sku: '', description: '' }); }
  create() {
    const isExpense = this.form.controls.purchase_type.value === 'expense';
    if (this.saving() || (!isExpense && this.form.invalid) || (isExpense && (!this.form.controls.expense_category.value || Number(this.form.controls.expense_amount.value) < 0 || this.lines.controls.some((line) => line.value.description && line.invalid)))) return;
    this.saving.set(true); this.error.set('');
    const value = this.form.getRawValue();
    this.api.createPurchase({ purchase_type: value.purchase_type, payment_type: value.payment_type, installment_count: value.installment_count, first_due_days: value.first_due_days, interval_days: value.interval_days, supplier_name: value.supplier_name || null, supplier_id: this.supplierByName(value.supplier_name)?.id ?? null, supplier_order_number: value.supplier_order_number || null, document_date: value.document_date || null, expense_category: value.expense_category || null, expense_amount: value.expense_amount || null, needed_by: value.needed_by || null, notes: value.notes || null, items: value.items.filter((item) => String(item.description || '').trim()).map((item) => ({ ...item, product_id: item.product_id || null })) }).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (purchase) => { this.showNew.set(false); this.purchases.update((list) => [purchase, ...list]); const files = this.selectedFiles(); if (files.length) { this.api.uploadPurchaseAttachments(purchase.id, files).subscribe({ next: (updated) => this.setPurchase(updated) }); } this.openDetails(purchase); }, error: (err) => this.error.set(err.error?.detail || 'Não foi possível salvar a compra.') });
  }
  setAttachments(files: FileList | null) { this.selectedFiles.set(files ? Array.from(files).slice(0, 10) : []); }
  uploadAttachments(purchase: Purchase, files: FileList | null) { const selected = files ? Array.from(files).slice(0, 10) : []; if (!selected.length) return; this.saving.set(true); this.api.uploadPurchaseAttachments(purchase.id, selected).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => this.setPurchase(updated), error: (err) => this.error.set(err.error?.detail || 'Não foi possível anexar os documentos.') }); }
  downloadAttachment(purchase: Purchase, attachment: Purchase['attachments'][number]) { this.api.downloadPurchaseAttachment(purchase.id, attachment.id, attachment.filename); }
  formatBytes(bytes: number) { return bytes < 1024 * 1024 ? `${Math.ceil(bytes / 1024)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`; }
  openDetails(purchase: Purchase) { this.closeRowMenu(); this.error.set(''); this.receiveValues.set(Object.fromEntries(purchase.items.map((item) => [item.id, { quantity: Math.max(0, item.quantity - item.received_quantity), productId: item.product_id || '', create: purchase.purchase_type === 'parts' && !item.product_id }]))); this.quoteCosts.set(Object.fromEntries(purchase.items.map((item) => [item.id, 0]))); this.quoteCostValidity.set({}); this.quoteTotalValue.set(null); this.quoteRounding.set(0); this.primeDrafts(purchase); this.draftEditor.set(false); this.detail.set(purchase); }
  availableProducts(stockType: 'product' | 'warehouse') { return this.products().filter((product) => product.stock_type === stockType); }
  selectedQuote(purchase: Purchase) { return purchase.quotes.find((quote) => quote.id === purchase.selected_quote_id) ?? null; }
  statusLabel(status: PurchaseStatus) { return this.statuses.find((entry) => entry.value === status)?.label ?? status; }
  purchaseStatusLabel(purchase: Purchase) { return this.statusLabel(purchase.status); }
  purchaseStatusNote(purchase: Purchase) {
    if (purchase.status === 'cancelled') return purchase.cancel_reason ? `Cancelada · ${purchase.cancel_reason}` : 'Compra cancelada.';
    if (purchase.status === 'closed') return 'Saldo pendente encerrado; o material recebido foi mantido no estoque.';
    return '';
  }
  payableLabel(payable: PurchasePayable) {
    if (payable.status === 'paid') return `Pago${payable.payment_method ? ' · ' + payable.payment_method : ''}`;
    if (payable.status === 'cancelled') return 'Encerrado com o cancelamento';
    if (payable.status === 'partial') return `Baixa parcial · vence ${this.dateLabel(payable.due_date)}`;
    return `Vence ${this.dateLabel(payable.due_date)}`;
  }
  dateLabel(value: string) { return new Date(value).toLocaleDateString('pt-BR'); }
  dateOnly(value: string | null | undefined) { return dateOnlyLabel(value); }
  isActive(purchase: Purchase) { return purchase.status !== 'cancelled' && purchase.status !== 'closed'; }
  hasReceived(purchase: Purchase) { return purchase.items.some((item) => item.received_quantity - (item.returned_quantity ?? 0) > 0); }
  stepIndex(status: PurchaseStatus) { if (status === 'cancelled') return -1; if (status === 'received' || status === 'closed') return 4; if (status === 'partially_received') return 3; return ['negotiating', 'approved', 'ordered'].indexOf(status); }
  progress(item: PurchaseItem) { return item.quantity ? Math.min(100, item.received_quantity / item.quantity * 100) : 0; }
  totalUnits(purchase: Purchase) { return purchase.items.reduce((sum, item) => sum + item.quantity, 0); }
  receivedUnits(purchase: Purchase) { return purchase.items.reduce((sum, item) => sum + item.received_quantity, 0); }
  receiveQty(item: PurchaseItem) { return this.receiveValues()[item.id]?.quantity ?? 0; }
  receiveObservation(item: PurchaseItem) { return this.receiveObservations()[item.id] ?? ''; }
  setReceiveObservation(item: PurchaseItem, value: string) { this.receiveObservations.update((values) => ({ ...values, [item.id]: value })); this.clearReceiptId(item); }
  setReceiveQty(item: PurchaseItem, value: string) { this.receiveValues.update((values) => ({ ...values, [item.id]: { ...values[item.id], quantity: Number(value) } })); this.clearReceiptId(item); }
  receiveProduct(item: PurchaseItem) { return this.receiveValues()[item.id]?.productId ?? ''; }
  setReceiveProduct(item: PurchaseItem, value: string) { this.receiveValues.update((values) => ({ ...values, [item.id]: { ...values[item.id], productId: value, create: false } })); this.clearReceiptId(item); }
  createNewProduct(item: PurchaseItem) { return this.receiveValues()[item.id]?.create ?? false; }
  setCreateNewProduct(item: PurchaseItem, value: boolean) { this.receiveValues.update((values) => ({ ...values, [item.id]: { ...values[item.id], create: value, productId: value ? '' : values[item.id]?.productId ?? '' } })); this.clearReceiptId(item); }
  quoteUnitCost(item: PurchaseItem) { return this.quoteCosts()[item.id] ?? 0; }
  quoteSubtotal(purchase: Purchase) { return purchase.items.reduce((sum, item) => sum + this.quoteUnitCost(item) * Number(item.quantity), 0); }
  /** O último campo editado manda: o total digitado prevalece; sem ele, o unitário alimenta o total. */
  quoteTotal(purchase: Purchase) { const typed = this.quoteTotalValue(); return typed === null ? this.quoteComputedTotal(purchase) : typed; }
  quoteComputedTotal(purchase: Purchase) { const value = this.quoteForm.getRawValue(); return this.round2(this.quoteSubtotal(purchase) + Number(value.freight_amount || 0) + Number(value.tax_amount || 0) - Number(value.discount_amount || 0)); }
  /** Líquido das peças: total − frete − impostos + desconto. Negativo é proposta impossível. */
  quoteNet(purchase: Purchase) { const value = this.quoteForm.getRawValue(); return this.round2(this.quoteTotal(purchase) - Number(value.freight_amount || 0) - Number(value.tax_amount || 0) + Number(value.discount_amount || 0)); }
  setQuoteConditionType(value: string) { this.quoteForm.controls.payment_type.setValue(value as PaymentConditionType); }
  setQuoteConditionNumber(field: 'installment_count' | 'first_due_days' | 'interval_days', value: string) { this.quoteForm.controls[field].setValue(Number(value) || 0); }
  applyQuoteConditionPreset(preset: 'cash' | '30' | '30/60' | '30/60/90') {
    if (preset === 'cash') { this.quoteForm.patchValue({ payment_type: 'cash', installment_count: 1, first_due_days: 0, interval_days: 30 }); return; }
    const days = preset.split('/').map((value) => Number(value));
    this.quoteForm.patchValue({ payment_type: days.length > 1 ? 'installments' : 'cash', installment_count: days.length, first_due_days: days[0], interval_days: days.length > 1 ? days[1] - days[0] : 30 });
  }
  /** Condição legível que será gravada no título a pagar. */
  quoteConditionPreview() {
    const value = this.quoteForm.getRawValue();
    if (value.payment_type === 'cash') { return value.first_due_days > 0 ? `à vista em ${value.first_due_days} dias` : 'à vista'; }
    const offsets = value.payment_type === 'entry'
      ? [value.first_due_days, ...Array.from({ length: value.installment_count }, (_, index) => value.first_due_days + (index + 1) * value.interval_days)]
      : Array.from({ length: value.installment_count }, (_, index) => value.first_due_days + index * value.interval_days);
    return (value.payment_type === 'entry' ? 'entrada + ' : '') + offsets.join('/');
  }

  /** Condição legível da proposta, igual à que será gravada no título a pagar (P12). */
  quoteConditionLabel(quote: PurchaseQuote) {
    if (!quote.payment_type || quote.payment_type === 'cash') { return quote.first_due_days ? `À vista em ${quote.first_due_days} dias` : 'À vista'; }
    const count = quote.installment_count ?? 1;
    const first = quote.first_due_days ?? 0;
    const interval = quote.interval_days ?? 30;
    const offsets = quote.payment_type === 'entry'
      ? [first, ...Array.from({ length: count }, (_, index) => first + (index + 1) * interval)]
      : Array.from({ length: count }, (_, index) => first + index * interval);
    return (quote.payment_type === 'entry' ? 'Entrada + ' : '') + offsets.join('/');
  }

  quoteDirectionNote() { return this.quoteTotalValue() === null ? 'o custo unitário de cada peça alimenta o total.' : 'o total digitado foi distribuído entre as peças pelo rateio escolhido.'; }
  quoteMismatch(purchase: Purchase) { return Math.abs(this.quoteComputedTotal(purchase) - this.quoteTotal(purchase)) > 0.01 * Math.max(1, purchase.items.length); }
  private round2(value: number) { return Math.round(value * 100) / 100; }
  setQuoteTotal(value: number | null) { const purchase = this.detail(); if (value === null) { this.quoteTotalValue.set(null); this.quoteRounding.set(0); return; } this.quoteTotalValue.set(value); if (purchase) this.distributeQuoteTotal(purchase, value); }
  /** Distribui o líquido da proposta pelos itens e fecha a sobra de centavos no maior item. */
  private distributeQuoteTotal(purchase: Purchase, total: number) {
    if (!purchase.items.length) return;
    const value = this.quoteForm.getRawValue();
    const netCents = Math.round((total - Number(value.freight_amount || 0) - Number(value.tax_amount || 0) + Number(value.discount_amount || 0)) * 100);
    const byQuantity = value.allocation_method === 'quantity';
    // A API serializa Decimal como texto: a quantidade chega como string e precisa ser número.
    let weights = purchase.items.map((item) => (byQuantity ? Number(item.quantity) : this.quoteUnitCost(item) * Number(item.quantity)));
    if (!byQuantity && weights.every((weight) => weight <= 0)) weights = purchase.items.map((item) => Number(item.quantity));
    const weightSum = weights.reduce((sum, weight) => sum + weight, 0);
    const shares = weights.map((weight) => (weightSum > 0 ? Math.round((netCents * weight) / weightSum) : 0));
    if (weightSum <= 0) shares[0] = netCents;
    const largest = weights.reduce((best, weight, index) => (weight > weights[best] ? index : best), 0);
    const residual = netCents - shares.reduce((sum, share) => sum + share, 0);
    shares[largest] += residual;
    const costs: Record<string, number> = {};
    purchase.items.forEach((item, index) => { costs[item.id] = this.round2(shares[index] / 100 / Number(item.quantity)); });
    this.quoteCosts.set(costs);
    // A sobra que aparece para o usuário é a diferença real entre o líquido digitado e a
    // soma dos unitários com duas casas, que nem sempre fecha em quantidades quebradas.
    const roundedSubtotal = purchase.items.reduce((sum, item) => sum + costs[item.id] * Number(item.quantity), 0);
    this.quoteRounding.set(this.round2(netCents / 100 - roundedSubtotal));
  }
  setQuoteUnitCost(item: PurchaseItem, value: number | null) { if (value === null) return; this.quoteTotalValue.set(null); this.quoteRounding.set(0); this.quoteCosts.update((costs) => ({ ...costs, [item.id]: value })); }
  setQuoteCostValidity(itemId: string, invalid: boolean) { this.quoteCostValidity.update((values) => ({ ...values, [itemId]: invalid })); }
  quoteCostHasErrors() { return Object.values(this.quoteCostValidity()).some(Boolean); }
  quoteCostsComplete(purchase: Purchase) { return purchase.items.every((item) => Number.isFinite(this.quoteUnitCost(item)) && this.quoteUnitCost(item) >= 0); }
  addQuote() { const purchase = this.detail(); if (!purchase || this.quoteForm.invalid || this.quoteCostHasErrors() || !this.quoteCostsComplete(purchase) || this.quoteTotal(purchase) < 0 || this.saving()) return; this.saving.set(true); this.error.set(''); const value = this.quoteForm.getRawValue(); this.api.addPurchaseQuote(purchase.id, { ...value, total: this.quoteTotal(purchase), item_costs: this.quoteCosts() }).pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => { this.setPurchase(updated); this.quoteForm.reset({ supplier_name: '', supplier_contact: '', freight_amount: 0, tax_amount: 0, discount_amount: 0, allocation_method: 'proportional', delivery_days: null, payment_type: 'cash', installment_count: 1, first_due_days: 30, interval_days: 30, payment_terms: '', notes: '' }); this.quoteCosts.set(Object.fromEntries(purchase.items.map((item) => [item.id, 0]))); this.quoteTotalValue.set(null); this.quoteRounding.set(0); }, error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar a cotação.') }); }
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
    this.api.receivePurchase(purchase.id, { items: [{ item_id: item.id, receipt_id: receiptId, quantity: choice.quantity, product_id: choice.productId || null, create_product: choice.create, observation: this.receiveObservation(item) || null }] }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.setPurchase(updated); this.clearReceiptId(item); this.api.products('', false).subscribe((items) => this.products.set(items)); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar o recebimento.')
    });
  }
  private clearReceiptId(item: PurchaseItem) { this.receiptIds.update((ids) => { const updated = { ...ids }; delete updated[item.id]; return updated; }); }
  openLifecycleForm(mode: 'cancel' | 'close') {
    const purchase = this.detail();
    if (!purchase) return;
    this.error.set('');
    this.lifecycleForm.set({ mode, reason: '', resolution: this.hasReceived(purchase) ? 'keep_received' : 'return_received' });
  }
  setLifecycleReason(value: string) { this.lifecycleForm.update((form) => form ? { ...form, reason: value } : form); }
  setLifecycleResolution(value: 'keep_received' | 'return_received') { this.lifecycleForm.update((form) => form ? { ...form, resolution: value } : form); }
  submitLifecycle(purchase: Purchase) {
    const form = this.lifecycleForm();
    if (!form || this.saving() || form.reason.trim().length < 3) return;
    const request = form.mode === 'cancel'
      ? this.api.cancelPurchaseWithReason(purchase.id, { reason: form.reason.trim(), resolution: form.resolution })
      : this.api.closePurchaseBalance(purchase.id, { reason: form.reason.trim() });
    this.saving.set(true); this.error.set('');
    request.pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.lifecycleForm.set(null); this.setPurchase(updated); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível concluir a ação.'),
    });
  }
  receiveAll(purchase: Purchase) {
    if (this.saving()) return;
    if (!confirm(`Receber todos os itens pendentes de ${purchase.number}? Itens sem produto vinculado serão cadastrados no catálogo.`)) return;
    this.saving.set(true); this.error.set('');
    this.api.receivePurchaseInFull(purchase.id, { create_products: true }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.setPurchase(updated); this.api.products('', false).subscribe((items) => this.products.set(items)); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar o recebimento.'),
    });
  }
  settlePayable(purchase: Purchase, payable: PurchasePayable) {
    if (this.saving()) return;
    const amount = payable.amount.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    if (!confirm(`Registrar o pagamento de ${amount} do título de ${purchase.number}?`)) return;
    this.saving.set(true); this.error.set('');
    this.api.settlePurchasePayable(purchase.id, payable.id).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: () => this.api.purchases().subscribe((items) => {
        this.purchases.set(items);
        const refreshed = items.find((item) => item.id === purchase.id);
        if (refreshed) this.detail.set(refreshed);
      }),
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível registrar o pagamento.'),
    });
  }
  requestDelete(purchase: Purchase, event?: Event) {
    event?.stopPropagation();
    this.closeRowMenu();
    this.error.set('');
    this.deleteReason.set('');
    this.deleteTarget.set(purchase);
  }
  cancelDelete() { this.deleteTarget.set(null); }
  deleteBlockedByPayment(purchase: Purchase) {
    return (purchase.payables ?? []).some((payable) => payable.status !== 'cancelled' && (payable.paid_amount ?? 0) > 0);
  }
  deletionEffects(purchase: Purchase) {
    const effects: string[] = [`${purchase.items.length} item(ns) do pedido`];
    if (purchase.quotes.length) effects.push(`${purchase.quotes.length} cotação(ões) registrada(s)`);
    if (purchase.attachments.length) effects.push(`${purchase.attachments.length} anexo(s), inclusive o arquivo armazenado`);
    const received = purchase.items.filter((item) => item.received_quantity - (item.returned_quantity ?? 0) > 0);
    if (received.length) {
      const quantity = received.reduce((sum, item) => sum + item.received_quantity - (item.returned_quantity ?? 0), 0);
      effects.push(`estorno de ${quantity} unidade(s) recebida(s) no estoque, com movimentação rastreável`);
    }
    const payable = (purchase.payables ?? []).find((entry) => entry.status !== 'cancelled');
    if (payable) effects.push(`título a pagar de ${Number(payable.amount).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' })}`);
    if (purchase.events.length) effects.push(`${purchase.events.length} evento(s) do histórico do pedido`);
    return effects;
  }
  confirmDelete(purchase: Purchase) {
    if (this.saving() || this.deleteBlockedByPayment(purchase)) return;
    this.saving.set(true); this.error.set('');
    const reason = this.deleteReason().trim();
    this.api.deletePurchase(purchase.id, reason || undefined).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        this.deleteTarget.set(null);
        if (this.detail()?.id === purchase.id) this.detail.set(null);
        this.purchases.update((items) => items.filter((item) => item.id !== purchase.id));
        this.message.set(`${purchase.number} foi excluída com os registros ligados.`);
      },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível excluir a compra.'),
    });
  }
  supplierByName(name: string | null | undefined) {
    const key = (name || '').trim().toLowerCase();
    return key ? this.suppliers().find((supplier) => supplier.name.toLowerCase() === key) ?? null : null;
  }
  applySupplierDefaults() {
    const supplier = this.supplierByName(this.form.controls.supplier_name.value);
    if (!supplier) return;
    if (supplier.default_delivery_days && !this.form.controls.needed_by.value) {
      const date = new Date();
      date.setDate(date.getDate() + supplier.default_delivery_days);
      this.form.controls.needed_by.setValue(date.toISOString().slice(0, 10));
    }
    if (supplier.default_payment_terms && !this.quoteForm.controls.payment_terms.value) {
      this.quoteForm.controls.payment_terms.setValue(supplier.default_payment_terms);
    }
  }
  registerSupplier(name: string) {
    const trimmed = (name || '').trim();
    if (trimmed.length < 2 || this.saving()) return;
    this.saving.set(true); this.error.set('');
    this.api.createSupplier({ name: trimmed }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (supplier) => { this.suppliers.update((items) => items.some((entry) => entry.id === supplier.id) ? items : [...items, { ...supplier, contact: null }]); this.applySupplierDefaults(); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível cadastrar o fornecedor.'),
    });
  }
  isOverdue(purchase: Purchase) {
    if (!purchase.needed_by || !['ordered', 'partially_received'].includes(purchase.status)) return false;
    const today = new Date();
    const todayKey = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}-${String(today.getDate()).padStart(2, '0')}`;
    return dateOnlyValue(purchase.needed_by) < todayKey;
  }
  purchaseTotal(purchase: Purchase) {
    if (purchase.purchase_type === 'expense') return purchase.expense_amount ?? 0;
    return purchase.total_amount ?? purchase.items.reduce((sum, item) => sum + item.quantity * (item.unit_cost ?? 0), 0);
  }
  totalPages() { return Math.max(1, Math.ceil(this.filtered().length / this.pageSize)); }
  pagedPurchases() { const page = Math.min(this.page(), this.totalPages()); const start = (page - 1) * this.pageSize; return this.filtered().slice(start, start + this.pageSize); }
  goToPage(delta: number) { this.page.set(Math.min(this.totalPages(), Math.max(1, this.page() + delta))); }
  isSelectable(purchase: Purchase) { return purchase.status === 'negotiating' && !purchase.selected_quote_id && purchase.items.every((item) => !item.received_quantity); }
  isSelected(id: string) { return !!this.selectedIds()[id]; }
  toggleSelection(id: string) { this.selectedIds.update((map) => ({ ...map, [id]: !map[id] })); }
  selectedPurchases() { return this.purchases().filter((purchase) => this.selectedIds()[purchase.id] && this.isSelectable(purchase)); }
  clearSelection() { this.selectedIds.set({}); }
  deleteSelectedDrafts() {
    const targets = this.selectedPurchases();
    if (!targets.length || this.saving()) return;
    if (!confirm(`Excluir ${targets.length} rascunho(s) selecionado(s)? Cada exclusão fica registrada no histórico de auditoria.`)) return;
    this.saving.set(true); this.error.set('');
    const failures: string[] = [];
    let pending = targets.length;
    for (const target of targets) {
      this.api.deletePurchase(target.id).pipe(finalize(() => { pending -= 1; if (!pending) { this.saving.set(false); this.clearSelection(); this.error.set(failures.join(' · ')); } })).subscribe({
        next: () => this.purchases.update((items) => items.filter((item) => item.id !== target.id)),
        error: (err) => failures.push(`${target.number}: ${err.error?.detail || 'falha ao excluir'}`),
      });
    }
  }
  openDraftEditor() { this.draftEditor.set(true); }
  closeDraftEditor() { this.draftEditor.set(false); }
  setDraftHeader(field: 'supplier_name' | 'supplier_order_number' | 'document_date' | 'needed_by' | 'notes', value: string) { this.draftHeader.update((header) => ({ ...header, [field]: value })); }
  saveDraftHeader(purchase: Purchase) {
    if (this.saving()) return;
    const header = this.draftHeader();
    this.saving.set(true); this.error.set('');
    this.api.updatePurchase(purchase.id, {
      supplier_name: header.supplier_name || null,
      supplier_id: this.supplierByName(header.supplier_name)?.id ?? null,
      supplier_order_number: header.supplier_order_number || null,
      document_date: header.document_date || null,
      needed_by: header.needed_by || null,
      notes: header.notes || null,
    }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível salvar os dados do pedido.'),
    });
  }
  setLineDraft(itemId: string, field: 'description' | 'sku' | 'unit' | 'quantity', value: string) {
    this.lineDrafts.update((drafts) => ({ ...drafts, [itemId]: { ...(drafts[itemId] ?? { description: '', sku: '', unit: 'un', quantity: 0 }), [field]: field === 'quantity' ? Number(value) : value } }));
  }
  saveLine(purchase: Purchase, item: PurchaseItem) {
    const draft = this.lineDrafts()[item.id];
    if (!draft || this.saving()) return;
    this.saving.set(true); this.error.set('');
    this.api.updatePurchaseItem(purchase.id, item.id, { description: draft.description, sku: draft.sku, unit: draft.unit, quantity: draft.quantity }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível salvar a peça.'),
    });
  }
  removePurchaseLine(purchase: Purchase, item: PurchaseItem) {
    if (this.saving()) return;
    if (!confirm(`Remover ${item.description} desta negociação?`)) return;
    this.saving.set(true); this.error.set('');
    this.api.removePurchaseItem(purchase.id, item.id).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => this.applyUpdate(updated),
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível remover a peça.'),
    });
  }
  setNewLineDraft(field: 'description' | 'sku' | 'unit' | 'quantity', value: string) {
    this.newLineDraft.update((draft) => ({ ...draft, [field]: field === 'quantity' ? Number(value) : value }));
  }
  addDraftLine(purchase: Purchase) {
    const draft = this.newLineDraft();
    if (!draft.description.trim() || draft.quantity <= 0 || this.saving()) return;
    this.saving.set(true); this.error.set('');
    this.api.addPurchaseItem(purchase.id, { description: draft.description.trim(), sku: draft.sku.trim(), unit: draft.unit.trim() || 'un', quantity: draft.quantity, unit_cost: 0 }).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: (updated) => { this.newLineDraft.set({ description: '', sku: '', unit: 'un', quantity: 1 }); this.applyUpdate(updated); },
      error: (err) => this.error.set(err.error?.detail || 'Não foi possível incluir a peça.'),
    });
  }
  private runAction(request: ReturnType<ApiService['placePurchaseOrder']>) { const purchase = this.detail(); if (!purchase) return; this.saving.set(true); this.error.set(''); request.pipe(finalize(() => this.saving.set(false))).subscribe({ next: (updated) => { this.setPurchase(updated); if (updated.status === 'received') this.api.products('', false, 'product').subscribe((items) => this.products.set(items)); }, error: (err) => this.error.set(err.error?.detail || 'Não foi possível atualizar esta compra.') }); }
  private primeDrafts(purchase: Purchase) {
    this.lineDrafts.set(Object.fromEntries(purchase.items.map((item) => [item.id, { description: item.description, sku: item.sku, unit: item.unit, quantity: item.quantity }])));
    this.draftHeader.set({ supplier_name: purchase.supplier_name || '', supplier_order_number: purchase.supplier_order_number || '', document_date: purchase.document_date ? purchase.document_date.slice(0, 10) : '', needed_by: purchase.needed_by ? purchase.needed_by.slice(0, 10) : '', notes: purchase.notes || '' });
  }
  private applyUpdate(purchase: Purchase) { this.primeDrafts(purchase); this.detail.set(purchase); this.purchases.update((items) => items.map((item) => item.id === purchase.id ? purchase : item)); }
  private setPurchase(purchase: Purchase) { this.applyUpdate(purchase); this.draftEditor.set(false); }
}
