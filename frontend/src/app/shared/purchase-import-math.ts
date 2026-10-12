/**
 * Rateio do documento importado (P0).
 *
 * Este é o espelho exato de `backend/app/services/purchase_allocation.py`: a revisão mostra
 * o mesmo custo final por peça e o mesmo fechamento que o backend grava, centavo a centavo.
 * O cálculo roda em inteiros (centavos e milésimos de unidade) para não depender do
 * arredondamento de ponto flutuante.
 */

export interface ImportLineDraft {
  quantity: number;
  unit_cost: number;
  discount_amount: number;
  /** Total impresso na linha do documento; quando existe, manda no fechamento. */
  line_total?: number | null;
}

export interface ImportDocumentDraft {
  total: number | null;
  shipping: number | null;
  discount: number | null;
  tax: number | null;
  /** P5: taxa de pagamento/processamento cobrada por fora do valor das peças. */
  extras: number | null;
}

export interface ImportPlanLine {
  base_unit_cost: number;
  unit_cost: number;
  freight_amount: number;
  tax_amount: number;
  extras_amount: number;
  discount_amount: number;
}

export interface ImportPlan {
  lines: ImportPlanLine[];
  items_subtotal: number;
  freight_amount: number;
  tax_amount: number;
  extras_amount: number;
  discount_amount: number;
  computed_total: number;
  document_total: number | null;
  total: number;
  difference: number;
}

/**
 * Proposta impossível. Quando o fechamento é o único problema, o erro carrega o rateio já
 * calculado para a revisão continuar mostrando os números ao lado do motivo.
 */
export class ImportPlanError extends Error {
  readonly plan: ImportPlan | null;

  constructor(message: string, plan: ImportPlan | null = null) {
    super(message);
    this.plan = plan;
  }
}

const MILLI = 1000;
const CENTS = 100;

export function toMilli(value: number | null | undefined): number {
  return Math.round(Number(value ?? 0) * MILLI);
}

export function toCents(value: number | null | undefined): number {
  return Math.round(Number(value ?? 0) * CENTS);
}

export function fromCents(cents: number): number {
  return Math.round(cents) / CENTS;
}

/** Divisão inteira com arredondamento half-up (metade para cima, em módulo). */
export function halfUpDiv(numerator: number, denominator: number): number {
  if (!denominator) throw new Error('Divisão por zero no rateio de valores.');
  const negative = numerator < 0 !== denominator < 0;
  const absoluteNumerator = Math.abs(numerator);
  const absoluteDenominator = Math.abs(denominator);
  const rounded = Math.floor(
    (2 * absoluteNumerator + absoluteDenominator) / (2 * absoluteDenominator),
  );
  return negative ? -rounded : rounded;
}

/** Rateia centavos por peso, fechando a sobra no maior item (o primeiro, em caso de empate). */
export function splitCents(
  amountCents: number,
  weights: Array<[string, number]>,
): Record<string, number> {
  const totalWeight = weights.reduce((sum, [, weight]) => sum + weight, 0);
  if (totalWeight <= 0) {
    return Object.fromEntries(weights.map(([key]) => [key, 0]));
  }
  const shares: Record<string, number> = {};
  for (const [key, weight] of weights) {
    shares[key] = halfUpDiv(amountCents * weight, totalWeight);
  }
  const residual = amountCents - Object.values(shares).reduce((sum, share) => sum + share, 0);
  if (residual) {
    let largestKey = weights[0][0];
    let largestWeight = weights[0][1];
    for (const [key, weight] of weights) {
      if (weight > largestWeight) {
        largestWeight = weight;
        largestKey = key;
      }
    }
    shares[largestKey] += residual;
  }
  return shares;
}

/** Formata centavos como `R$ 1.234,56`, igual à mensagem do backend. */
export function formatBrlCents(cents: number): string {
  const sign = cents < 0 ? '-' : '';
  const absolute = Math.abs(Math.round(cents));
  const integer = Math.floor(absolute / CENTS);
  const fraction = String(absolute % CENTS).padStart(2, '0');
  return `${sign}R$ ${String(integer).replace(/\B(?=(\d{3})+(?!\d))/g, '.')},${fraction}`;
}

export function buildImportPlan(
  lines: ImportLineDraft[],
  document: ImportDocumentDraft,
): ImportPlan {
  if (!lines.length) {
    throw new ImportPlanError('Adicione pelo menos uma peça antes de confirmar a importação.');
  }

  const lineBaseCents: number[] = [];
  const quantityMilli: number[] = [];
  for (const line of lines) {
    const milli = toMilli(line.quantity);
    if (milli <= 0) {
      throw new ImportPlanError('Informe uma quantidade maior que zero em todas as peças.');
    }
    let lineNet = milli * toCents(line.unit_cost) - MILLI * toCents(line.discount_amount);
    if (lineNet < 0) {
      throw new ImportPlanError(
        'O desconto da linha é maior que o total desta peça. Revise o desconto.',
      );
    }
    if (line.line_total != null && line.line_total > 0) {
      // O papel arredonda o unitário na vitrine (20 × 6,43 = 128,60) e cobra o total exato
      // da linha (128,42): recalcular por unidade criaria centavos de diferença no fechamento.
      lineNet = toCents(line.line_total) * MILLI;
    }
    quantityMilli.push(milli);
    lineBaseCents.push(lineNet);
  }
  const baseCents = lineBaseCents.map((cents, index) => halfUpDiv(cents, quantityMilli[index]));

  const weights: Array<[string, number]> = lineBaseCents.map((cents, index) => [
    String(index),
    cents,
  ]);
  const freightCents = toCents(document.shipping);
  const taxCents = toCents(document.tax);
  const extrasCents = toCents(document.extras);
  const discountCents = toCents(document.discount);
  const freightShare = splitCents(freightCents, weights);
  const taxShare = splitCents(taxCents, weights);
  const extrasShare = splitCents(extrasCents, weights);
  const discountShare = splitCents(discountCents, weights);

  const documentCents = document.total === null ? null : toCents(document.total);
  const adjustmentsCents = freightCents + taxCents + extrasCents - discountCents;
  if (documentCents !== null && adjustmentsCents > documentCents) {
    throw new ImportPlanError(
      'O frete, os impostos e as taxas extras menos o desconto superam o total do ' +
        'documento. Revise os valores.',
    );
  }

  const planLines: ImportPlanLine[] = lines.map((_, index) => {
    const extraCents =
      freightShare[String(index)] +
      taxShare[String(index)] +
      extrasShare[String(index)] -
      discountShare[String(index)];
    const landedCents = baseCents[index] + halfUpDiv(extraCents * MILLI, quantityMilli[index]);
    if (landedCents < 0) {
      throw new ImportPlanError(
        'Os descontos deixam o custo de alguma peça negativo. Revise frete, impostos, ' +
          'taxas extras e desconto.',
      );
    }
    return {
      base_unit_cost: fromCents(baseCents[index]),
      unit_cost: fromCents(landedCents),
      freight_amount: fromCents(freightShare[String(index)]),
      tax_amount: fromCents(taxShare[String(index)]),
      extras_amount: fromCents(extrasShare[String(index)]),
      discount_amount: fromCents(discountShare[String(index)]),
    };
  });

  const subtotalCents = halfUpDiv(
    lineBaseCents.reduce((sum, cents) => sum + cents, 0),
    MILLI,
  );
  const computedCents = subtotalCents + adjustmentsCents;
  if (computedCents < 0) {
    throw new ImportPlanError(
      'O total é menor que o frete, os impostos e as taxas extras menos o desconto. ' +
        'Revise os valores.',
    );
  }
  let differenceCents = 0;
  let totalCents = computedCents;
  if (documentCents !== null) {
    differenceCents = computedCents - documentCents;
    totalCents = documentCents;
  }
  const plan: ImportPlan = {
    lines: planLines,
    items_subtotal: fromCents(subtotalCents),
    freight_amount: fromCents(freightCents),
    tax_amount: fromCents(taxCents),
    extras_amount: fromCents(extrasCents),
    discount_amount: fromCents(discountCents),
    computed_total: fromCents(computedCents),
    document_total: documentCents === null ? null : fromCents(documentCents),
    total: fromCents(totalCents),
    difference: fromCents(differenceCents),
  };
  if (documentCents !== null && Math.abs(differenceCents) > lines.length) {
    throw new ImportPlanError(
      'A soma dos itens não fecha com o total do documento: a diferença é de ' +
        `${formatBrlCents(Math.abs(differenceCents))}. Confira itens, frete, impostos, ` +
        'taxas extras e desconto.',
      plan,
    );
  }
  return plan;
}
