import { describe, expect, it } from 'vitest';
import { visibleNavigationSections } from './navigation';

describe('sidebar navigation', () => {
  it('organizes pages by business flow', () => {
    const sections = visibleNavigationSections('admin');

    expect(sections.map((section) => section.label)).toEqual([
      'Vendas e clientes',
      'Estoque e compras',
      'Financeiro',
      'Análise',
    ]);
    expect(sections[0].items.map((item) => item.path)).toEqual([
      '/marketplace',
      '/invoices',
      '/customers',
    ]);
    expect(sections[1].items.map((item) => item.path)).toEqual(['/products', '/purchases']);
    expect(sections[3].items.map((item) => item.path)).toContain('/vehicle-market');
  });

  it('keeps only pages available to the current role', () => {
    const stockPaths = visibleNavigationSections('stock').flatMap((section) =>
      section.items.map((item) => item.path),
    );
    const operatorPaths = visibleNavigationSections('operator').flatMap((section) =>
      section.items.map((item) => item.path),
    );

    expect(stockPaths).toContain('/products');
    expect(stockPaths).toContain('/purchases');
    expect(stockPaths).not.toContain('/finance');
    expect(stockPaths).not.toContain('/customers');
    expect(operatorPaths).toContain('/customers');
    expect(operatorPaths).not.toContain('/purchases');
  });
});
