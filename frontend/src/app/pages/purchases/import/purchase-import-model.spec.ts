import { describe, expect, it } from 'vitest';

import {
  closingDifference,
  emptyImportDraft,
  emptyImportLine,
  hasItemsToCheck,
  importBlockers,
  itemsTotal,
  needsRate,
  paidDifference,
  subtotalDifference,
} from './purchase-import-model';

function draftWith(overrides: Partial<ReturnType<typeof emptyImportDraft>> = {}) {
  return { ...emptyImportDraft(), ...overrides };
}

describe('revisão de importação — contas puras', () => {
  it('fecha a diferença do documento com itens, frete, impostos e desconto', () => {
    const draft = draftWith({
      total: 100,
      shipping: 10,
      tax: 5,
      discount: 2,
      items: [
        { ...emptyImportLine(), line_total: 87 },
        { ...emptyImportLine(), line_total: 0 },
      ],
    });
    expect(itemsTotal(draft.items)).toBe(87);
    expect(closingDifference(draft)).toBe(0);
    expect(closingDifference({ ...draft, total: 90 })).toBe(10);
  });

  it('não compara fechamento quando o documento não trouxe total ou não há itens', () => {
    expect(closingDifference(draftWith({ total: null }))).toBe(0);
    expect(closingDifference(draftWith({ total: 100 }))).toBe(0);
    expect(subtotalDifference(draftWith({ total: 100 }), null)).toBeNull();
  });

  it('compara o subtotal lido do documento com a soma das linhas', () => {
    const draft = draftWith({ items: [{ ...emptyImportLine(), line_total: 40 }] });
    expect(subtotalDifference(draft, 40)).toBe(0);
    expect(subtotalDifference(draft, 41.5)).toBe(-1.5);
  });

  it('mostra a diferença entre o valor pago e o total', () => {
    expect(paidDifference(draftWith({ total: 310.34, paidAmount: 319.65 }))).toBe(9.31);
    expect(paidDifference(draftWith({ total: 10, paidAmount: null }))).toBe(0);
  });

  it('inclui as taxas extras no fechamento do documento', () => {
    // Recibo do Alibaba: 128,42 de itens + 181,92 de frete + 9,31 de taxa = 319,65 pago.
    const draft = draftWith({
      total: 319.65,
      shipping: 181.92,
      extras: 9.31,
      items: [{ ...emptyImportLine(), line_total: 128.42 }],
    });
    expect(closingDifference(draft)).toBe(0);
    // Sem contar a taxa, o mesmo documento acusaria a diferença que bloqueava a importação.
    expect(closingDifference({ ...draft, extras: 0 })).toBe(-9.31);
  });

  it('exige cotação apenas quando o documento não está em reais', () => {
    expect(needsRate('USD')).toBe(true);
    expect(needsRate('brl')).toBe(false);
    expect(needsRate(null)).toBe(false);
  });

  it('só pede conferência de itens quando há linha ou total lido', () => {
    expect(hasItemsToCheck(null, draftWith())).toBe(false);
    expect(hasItemsToCheck({ items_total: 12 } as never, draftWith())).toBe(true);
  });
});

describe('revisão de importação — bloqueios de confirmação', () => {
  const base = { needsRate: false, moneyInvalid: false, kind: 'parts' as const, category: '' };

  it('exige SKU ou produto vinculado em cada linha', () => {
    const draft = draftWith({ items: [{ ...emptyImportLine(), description: 'Filtro' }] });
    const blockers = importBlockers({ ...base, draft, duplicate: null });
    expect(blockers).toContain(
      'Informe o SKU ou vincule um produto na linha 1: a compra já nasce como pedido registrado.',
    );
  });

  it('bloqueia desconto maior que o valor da linha', () => {
    const draft = draftWith({
      items: [
        {
          ...emptyImportLine(),
          description: 'Filtro',
          sku: 'F-1',
          quantity: 1,
          unit_cost: 10,
          discount_amount: 11,
        },
      ],
    });
    expect(importBlockers({ ...base, draft, duplicate: null })).toContain(
      'O desconto da linha 1 é maior que o valor da linha.',
    );
  });

  it('avisa quando o mesmo documento já foi importado', () => {
    const draft = draftWith({ items: [] });
    const blockers = importBlockers({
      ...base,
      draft,
      duplicate: {
        purchase_id: 'p1',
        purchase_number: 'CMP-9',
        purchase_status: 'received',
        cancelled: false,
      },
    });
    expect(blockers[0]).toBe('Este documento já foi importado na compra CMP-9.');
  });

  it('na despesa, cobra categoria e valor total em vez das linhas', () => {
    const draft = draftWith({ total: 0 });
    const blockers = importBlockers({ ...base, kind: 'expense', draft, duplicate: null });
    expect(blockers).toEqual([
      'Escolha a categoria da despesa.',
      'Informe o valor total da despesa.',
    ]);
  });

  it('junta os mesmos motivos uma única vez', () => {
    const draft = draftWith({
      total: 10,
      items: [
        { ...emptyImportLine(), description: 'A' },
        { ...emptyImportLine(), description: 'B' },
      ],
    });
    const blockers = importBlockers({ ...base, draft, duplicate: null });
    expect(new Set(blockers).size).toBe(blockers.length);
  });
});
