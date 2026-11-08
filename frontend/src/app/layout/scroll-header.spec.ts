import { trackHeaderScroll } from './scroll-header';

describe('mobile header on scroll', () => {
  it('ignores small movements and returns on upward travel without reaching the top', () => {
    const hidden = trackHeaderScroll({ pivot: 0, hidden: false }, 150, 50);
    expect(hidden.hidden).toBe(true);
    const jitter = trackHeaderScroll(hidden, 146, 50);
    expect(jitter.hidden).toBe(true);
    const visible = trackHeaderScroll(jitter, 134, 50);
    expect(visible.hidden).toBe(false);
    expect(trackHeaderScroll(visible, 142, 50).hidden).toBe(false);
    expect(trackHeaderScroll(visible, 154, 50).hidden).toBe(true);
  });

  it('stays visible near the top and when returned there', () => {
    expect(trackHeaderScroll({ pivot: 0, hidden: false }, 40, 50).hidden).toBe(false);
    expect(trackHeaderScroll({ pivot: 17, hidden: true }, 10, 50).hidden).toBe(false);
  });
});
