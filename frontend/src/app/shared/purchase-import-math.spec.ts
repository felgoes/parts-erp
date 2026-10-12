import {
  ImportPlanError,
  buildImportPlan,
  formatBrlCents,
  halfUpDiv,
} from './purchase-import-math';

const noDocument = { total: null, shipping: 0, discount: 0, tax: 0, extras: 0 };

describe('buildImportPlan', () => {
  it('keeps the same closing the backend stores for the imported document', () => {
    const plan = buildImportPlan([{ quantity: 2, unit_cost: 50, discount_amount: 0 }], {
      total: 112,
      shipping: 10,
      tax: 5,
      extras: 0,
      discount: 3,
    });

    expect(plan.total).toBe(112);
    expect(plan.items_subtotal).toBe(100);
    expect(plan.difference).toBe(0);
    expect(plan.lines[0]).toEqual({
      base_unit_cost: 50,
      unit_cost: 56,
      freight_amount: 10,
      tax_amount: 5,
      extras_amount: 0,
      discount_amount: 3,
    });
  });

  it('closes the cent residue on the largest item across several lines', () => {
    const plan = buildImportPlan(
      [
        { quantity: 1, unit_cost: 10, discount_amount: 0 },
        { quantity: 1, unit_cost: 10, discount_amount: 0 },
        { quantity: 1, unit_cost: 10.01, discount_amount: 0 },
      ],
      { ...noDocument, shipping: 10 },
    );

    expect(plan.total).toBe(40.01);
    expect(plan.lines.reduce((sum, line) => sum + line.freight_amount, 0)).toBeCloseTo(10, 2);
    expect(plan.lines.map((line) => line.freight_amount)).toEqual([3.33, 3.33, 3.34]);
    expect(plan.lines.map((line) => line.unit_cost)).toEqual([13.33, 13.33, 13.35]);
  });

  it('blocks a document whose total does not close and shows the difference', () => {
    expect(() =>
      buildImportPlan([{ quantity: 2, unit_cost: 50, discount_amount: 0 }], {
        total: 300,
        shipping: 10,
        tax: 5,
        extras: 0,
        discount: 3,
      }),
    ).toThrowError(/diferença é de R\$ 188,00/);
  });

  it('keeps the computed breakdown visible when only the closing fails', () => {
    try {
      buildImportPlan([{ quantity: 2, unit_cost: 50, discount_amount: 0 }], {
        total: 300,
        shipping: 10,
        tax: 5,
        extras: 0,
        discount: 3,
      });
      throw new Error('A revisão deveria bloquear o documento');
    } catch (error) {
      expect(error).toBeInstanceOf(ImportPlanError);
      const plan = (error as ImportPlanError).plan;
      expect(plan?.computed_total).toBe(112);
      expect(plan?.document_total).toBe(300);
      expect(plan?.difference).toBe(-188);
      expect(plan?.lines[0].unit_cost).toBe(56);
    }
  });

  it('blocks freight and taxes above the document total', () => {
    expect(() =>
      buildImportPlan([{ quantity: 1, unit_cost: 10, discount_amount: 0 }], {
        total: 10,
        shipping: 20,
        tax: 0,
        extras: 0,
        discount: 0,
      }),
    ).toThrowError(/superam o total do documento/);
  });

  it('blocks a line discount bigger than the line itself', () => {
    expect(() =>
      buildImportPlan([{ quantity: 1, unit_cost: 10, discount_amount: 15 }], noDocument),
    ).toThrowError(/desconto da linha/);
  });

  it('requires at least one line', () => {
    expect(() => buildImportPlan([], noDocument)).toThrowError(ImportPlanError);
  });

  it('turns the line discount into the net unit cost of that line', () => {
    const plan = buildImportPlan([{ quantity: 2, unit_cost: 10, discount_amount: 4 }], noDocument);

    expect(plan.lines[0].base_unit_cost).toBe(8);
    expect(plan.total).toBe(16);
  });
});

describe('halfUpDiv', () => {
  it('rounds exact halves up in both directions', () => {
    expect(halfUpDiv(1, 2)).toBe(1);
    expect(halfUpDiv(3, 2)).toBe(2);
    expect(halfUpDiv(-1, 2)).toBe(-1);
    expect(halfUpDiv(5, 2)).toBe(3);
  });
});

describe('formatBrlCents', () => {
  it('formats cents the same way the backend message does', () => {
    expect(formatBrlCents(18800)).toBe('R$ 188,00');
    expect(formatBrlCents(123456789)).toBe('R$ 1.234.567,89');
    expect(formatBrlCents(-5)).toBe('-R$ 0,05');
  });
});
