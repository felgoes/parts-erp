export interface ProductListView {
  search: string;
  stockTab: 'product' | 'warehouse';
  onlyLow: boolean;
  scrollY: number;
}

export interface ProductListAction {
  type: 'edit' | 'adjust' | 'listing';
  id: string;
}

const VIEW_KEY = 'parts-erp.products-list-view';

export function restoreProductListView(lowStockEntry = false): ProductListView {
  if (lowStockEntry) return { stockTab: 'product', search: '', onlyLow: true, scrollY: 0 };
  try {
    const value = JSON.parse(sessionStorage.getItem(VIEW_KEY) || '{}');
    return {
      search: typeof value.search === 'string' ? value.search : '',
      stockTab: value.stockTab === 'warehouse' ? 'warehouse' : 'product',
      onlyLow: value.onlyLow === true,
      scrollY: Number.isFinite(value.scrollY) ? value.scrollY : 0,
    };
  } catch {
    return { search: '', stockTab: 'product', onlyLow: false, scrollY: 0 };
  }
}

export function saveProductListView(view: ProductListView): void {
  try {
    sessionStorage.setItem(VIEW_KEY, JSON.stringify(view));
  } catch {
    // Retorno e filtros continuam disponíveis durante a navegação atual.
  }
}

export function takeProductListAction(): ProductListAction | null {
  const state = window.history.state;
  if (!['edit', 'adjust', 'listing'].includes(state?.productAction) || !state?.productId) return null;
  window.history.replaceState({ ...state, productAction: null, productId: null }, '');
  return { type: state.productAction, id: state.productId };
}
