import { describe, expect, it } from 'vitest';
import { panelBounds } from './assistant-viewport';

describe('panelBounds', () => {
  it('mantém o CSS padrão no desktop sem teclado', () => {
    expect(
      panelBounds({ width: 1200, height: 800, offsetTop: 0, offsetLeft: 0 }, 800, false),
    ).toBeNull();
  });

  it('ocupa a área visível no celular', () => {
    const bounds = panelBounds(
      { width: 390, height: 844, offsetTop: 0, offsetLeft: 0 },
      844,
      true,
    );
    expect(bounds).toEqual({
      top: 8,
      left: 8,
      width: 374,
      height: 828,
      keyboard: false,
    });
  });

  it('sobe o painel quando o teclado encolhe o visual viewport', () => {
    const bounds = panelBounds(
      { width: 390, height: 380, offsetTop: 464, offsetLeft: 0 },
      844,
      true,
    );
    expect(bounds?.keyboard).toBe(true);
    expect(bounds?.top).toBe(472);
    expect(bounds?.height).toBe(364);
  });
});
