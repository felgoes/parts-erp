import { decisionLabel, trendWidth } from './market-study-view';

describe('market-study presentation', () => {
  it('labels supplier negotiation without implying a purchase recommendation', () => {
    expect(decisionLabel('negociar_fornecedor')).toBe('Negociar fornecedor');
    expect(decisionLabel(null)).toBe('Em triagem');
  });

  it('sizes a trend bar only from the observed series', () => {
    expect(trendWidth(25, [{ value: 50 }, { value: 25 }])).toBe(50);
    expect(trendWidth(0, [])).toBe(0);
  });
});
