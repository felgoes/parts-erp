import { dateOnlyLabel, dateOnlyValue } from './date-only';

describe('dateOnlyLabel', () => {
  it('keeps the calendar day stored as UTC midnight', () => {
    expect(dateOnlyLabel('2026-10-05T00:00:00Z')).toBe('05/10/2026');
    expect(dateOnlyLabel('2026-10-05')).toBe('05/10/2026');
  });

  it('handles empty values', () => {
    expect(dateOnlyLabel(null)).toBe('');
    expect(dateOnlyValue(undefined)).toBe('');
  });
});
