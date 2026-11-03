import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  restoreProductListView,
  saveProductListView,
  takeProductListAction,
} from './product-list-context';

describe('product list context', () => {
  beforeEach(() => {
    sessionStorage.clear();
    window.history.replaceState({}, '');
  });

  afterEach(() => {
    sessionStorage.clear();
    window.history.replaceState({}, '');
  });

  it('restores the default list when there is no saved context', () => {
    expect(restoreProductListView()).toEqual({
      search: '',
      stockTab: 'product',
      onlyLow: false,
      scrollY: 0,
    });
  });

  it('round trips filters, tab and scroll position', () => {
    const view = { search: 'filtro', stockTab: 'warehouse' as const, onlyLow: true, scrollY: 380 };
    saveProductListView(view);
    expect(restoreProductListView()).toEqual(view);
  });

  it('consumes a pending action once and clears it from browser history', () => {
    window.history.replaceState({ productAction: 'adjust', productId: 'product-42' }, '');
    expect(takeProductListAction()).toEqual({ type: 'adjust', id: 'product-42' });
    expect(takeProductListAction()).toBeNull();
    expect(window.history.state.productAction).toBeNull();
  });

  it('ignores malformed or unsupported actions', () => {
    window.history.replaceState({ productAction: 'delete', productId: 'product-42' }, '');
    expect(takeProductListAction()).toBeNull();
  });
});
