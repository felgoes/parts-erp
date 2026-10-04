import { describe, expect, it } from 'vitest';
import { quickDateRange } from './quick-date-ranges';

describe('quick date ranges', () => {
  const now = new Date(2026, 9, 4, 18);

  it('uses inclusive rolling ranges ending today', () => {
    expect(quickDateRange('last7', now)).toEqual({ startDate: '2026-09-28', endDate: '2026-10-04' });
    expect(quickDateRange('last30', now)).toEqual({ startDate: '2026-09-05', endDate: '2026-10-04' });
  });

  it('uses calendar-aligned month and year ranges', () => {
    expect(quickDateRange('thisMonth', now)).toEqual({ startDate: '2026-10-01', endDate: '2026-10-04' });
    expect(quickDateRange('lastMonth', now)).toEqual({ startDate: '2026-09-01', endDate: '2026-09-30' });
    expect(quickDateRange('thisYear', now)).toEqual({ startDate: '2026-01-01', endDate: '2026-10-04' });
  });

  it('handles the year boundary for the previous month', () => {
    expect(quickDateRange('lastMonth', new Date(2026, 0, 8))).toEqual({
      startDate: '2025-12-01',
      endDate: '2025-12-31',
    });
  });
});
