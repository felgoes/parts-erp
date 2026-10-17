/**
 * Modelo e contas puras da revisão de importação de documento (P0/P14).
 *
 * Nada aqui conhece a tela: são tipos e funções que recebem o rascunho e devolvem números,
 * textos e bloqueios. Ficou separado da página de compras para as duas leituras ficarem
 * menores e para as regras de fechamento serem testáveis sem montar componente.
 */

export interface ImportDraftItem {
  description: string;
  sku: string;
  quantity: number;
  unit_cost: number;
  confidence: number;
  product_id: string | null;
  stock_controlled: boolean;
  line_total: number;
  discount_amount: number;
  source: string;
  quantityDerived: boolean;
}

/** Estado da revisão de importação: campos do documento, rateio e linhas. */
export interface ImportDraft {
  supplier: string;
  orderNumber: string;
  documentDate: string;
  total: number | null;
  shipping: number | null;
  discount: number | null;
  tax: number | null;
  /** P5: taxa de pagamento/processamento cobrada por fora do valor das peças. */
  extras: number | null;
  currency: string | null;
  exchangeRate: number | null;
  paidAmount: number | null;
  items: ImportDraftItem[];
}

/** Fechamento lido do documento, para comparar com o que o usuário está vendo. */
export interface ImportCheck {
  items_total: number | null;
  subtotal?: number | null;
  closing_difference: number | null;
  subtotal_difference: number | null;
  balanced: boolean;
}

/** Documento já importado, quando o mesmo papel aparece duas vezes. */
export interface ImportDuplicate {
  purchase_id: string;
  purchase_number: string;
  purchase_status: string;
  cancelled: boolean;
}

/** Cadastro de peça aberto dentro da revisão. */
export interface ImportProductDraft {
  sku: string;
  stock_type: 'product' | 'warehouse';
  name: string;
  description: string;
  sale_price: number;
  cost_price: number;
  minimum_stock: number;
  brand: string;
  manufacturer: string;
  manufacturer_part_number: string;
  barcode: string;
  category: string;
  item_condition: 'new' | 'used' | 'refurbished';
  warranty_days: number | null;
  origin_country: string;
  weight_g: number | null;
  package_length_cm: number | null;
  package_width_cm: number | null;
  package_height_cm: number | null;
}

export function emptyImportDraft(): ImportDraft {
  return {
    supplier: '',
    orderNumber: '',
    documentDate: '',
    total: null,
    shipping: null,
    discount: null,
    tax: null,
    extras: null,
    currency: null,
    exchangeRate: null,
    paidAmount: null,
    items: [],
  };
}

/** Categorias de despesa oferecidas na revisão e no cadastro de despesa da página. */
export const EXPENSE_CATEGORIES = [
  'Aluguel',
  'Energia e água',
  'Internet e telefonia',
  'Contabilidade',
  'Marketing',
  'Frete e transporte',
  'Material de escritório',
  'Materiais de consumo e embalagem',
  'Impostos e taxas',
  'Serviços',
  'Outros',
];

export function emptyImportProductDraft(): ImportProductDraft {
  return {
    sku: '',
    stock_type: 'product',
    name: '',
    description: '',
    sale_price: 0,
    cost_price: 0,
    minimum_stock: 0,
    brand: '',
    manufacturer: '',
    manufacturer_part_number: '',
    barcode: '',
    category: '',
    item_condition: 'new',
    warranty_days: null,
    origin_country: '',
    weight_g: null,
    package_length_cm: null,
    package_width_cm: null,
    package_height_cm: null,
  };
}

export function emptyImportLine(): ImportDraftItem {
  return {
    description: '',
    sku: '',
    quantity: 1,
    unit_cost: 0,
    confidence: 0,
    product_id: null,
    stock_controlled: true,
    line_total: 0,
    discount_amount: 0,
    source: '',
    quantityDerived: false,
  };
}

export function today(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
}

export function fieldOriginText(
  field: { source?: string; confidence?: number } | undefined,
): string {
  if (!field) return 'não identificado';
  const source = String(field.source || '');
  if (source === 'xml') return 'XML da NF-e';
  if (source === 'ocr')
    return `OCR · qualidade ${Math.round((Number(field.confidence) || 0) * 100)}%`;
  if (source === 'pdf_text') return 'texto do documento';
  if (source === 'columns') return 'grade do documento';
  return 'documento';
}

export function itemOriginText(item: {
  source?: string;
  confidence?: number;
  quantity_derived?: boolean;
  quantityDerived?: boolean;
}): string {
  const base = fieldOriginText(item);
  const derived = item.quantity_derived ?? item.quantityDerived;
  return derived ? `${base} · quantidade derivada` : base;
}

export function itemsTotal(items: readonly ImportDraftItem[]): number {
  return items.reduce((sum, item) => sum + Number(item.line_total || 0), 0);
}

export function closingDifference(draft: ImportDraft): number {
  if (draft.total === null || !draft.items.length) return 0;
  return Number(
    (
      itemsTotal(draft.items) +
      Number(draft.shipping || 0) +
      Number(draft.tax || 0) +
      Number(draft.extras || 0) -
      Number(draft.discount || 0) -
      Number(draft.total)
    ).toFixed(2),
  );
}

export function subtotalDifference(draft: ImportDraft, subtotal: number | null): number | null {
  if (subtotal === null || !draft.items.length) return null;
  return Number((itemsTotal(draft.items) - Number(subtotal)).toFixed(2));
}

export function paidDifference(draft: ImportDraft): number {
  if (draft.paidAmount === null || draft.total === null) return 0;
  return Number((Number(draft.paidAmount) - Number(draft.total)).toFixed(2));
}

export function needsRate(currency: string | null): boolean {
  return !!currency && currency.toUpperCase() !== 'BRL';
}

export function hasItemsToCheck(check: ImportCheck | null, draft: ImportDraft): boolean {
  return !!check?.items_total || draft.items.length > 0;
}

/**
 * Material de despesa que vira item da compra. Basta a linha estar marcada como controlada no
 * estoque: exigir o produto vinculado aqui descartava a linha em silêncio, e o produto pode ser
 * criado no recebimento (o painel de detalhe oferece "Criar produto no catálogo ao receber").
 */
export function expenseMaterialLines(items: readonly ImportDraftItem[]): ImportDraftItem[] {
  return items.filter((item) => item.stock_controlled);
}

/** Motivos visíveis que impedem a confirmação — ninguém fica preso sem saber por quê. */
export function importBlockers(input: {
  draft: ImportDraft;
  duplicate: ImportDuplicate | null;
  needsRate: boolean;
  moneyInvalid: boolean;
  kind: 'parts' | 'expense';
  category: string;
}): string[] {
  const blockers: string[] = [];
  const { draft, duplicate } = input;
  if (duplicate && !duplicate.cancelled) {
    blockers.push(`Este documento já foi importado na compra ${duplicate.purchase_number}.`);
  }
  if (input.needsRate && !(Number(draft.exchangeRate) > 0)) {
    blockers.push('Informe a cotação usada na conversão para reais.');
  }
  if (input.moneyInvalid) {
    blockers.push('Há um campo de valor com formato inválido — corrija o valor destacado.');
  }
  if (input.kind === 'expense') {
    if (input.category.trim().length < 2) blockers.push('Escolha a categoria da despesa.');
    if (!(Number(draft.total) > 0)) blockers.push('Informe o valor total da despesa.');
    return blockers;
  }
  if (!draft.items.length) {
    blockers.push('Inclua pelo menos um item — ou marque uma linha candidata do documento.');
  }
  draft.items.forEach((item, index) => {
    const label = `linha ${index + 1}`;
    if (item.description.trim().length < 2) blockers.push(`Descreva a ${label}.`);
    if (!(Number(item.quantity) > 0)) blockers.push(`Informe a quantidade da ${label}.`);
    if (item.stock_controlled && !item.product_id) {
      blockers.push(
        `Vincule um produto do catálogo na ${label} (ou desmarque "Controlado no estoque").`,
      );
    }
    // P0, regra 6: a compra nasce com o pedido registrado, então cada linha precisa de SKU
    // ou produto vinculado — a mesma exigência do envio manual do pedido.
    if (!item.sku.trim() && !item.product_id) {
      blockers.push(
        `Informe o SKU ou vincule um produto na ${label}: a compra já nasce como pedido registrado.`,
      );
    }
    if (Number(item.discount_amount) > Number(item.quantity) * Number(item.unit_cost)) {
      blockers.push(`O desconto da ${label} é maior que o valor da linha.`);
    }
  });
  return [...new Set(blockers)];
}

export function importNotes(
  profileName: string,
  draft: Pick<
    ImportDraft,
    'orderNumber' | 'documentDate' | 'total' | 'shipping' | 'discount' | 'tax'
  >,
): string {
  const metadata = [
    `Perfil: ${profileName}`,
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
