import { describe, expect, it } from 'vitest';
import { groupTrackingHistory } from './tracking-history';

describe('tracking history', () => {
  it('groups consecutive updates with the same status', () => {
    const groups = groupTrackingHistory([
      {
        status: 'ready_to_ship',
        detail: 'invoice_pending',
        created_at: '2026-10-24T10:00:00Z',
      },
      {
        status: 'ready-to-ship',
        detail: 'ready_to_print',
        created_at: '2026-10-24T10:10:00Z',
      },
      {
        status: 'shipped',
        detail: 'out_for_delivery',
        created_at: '2026-10-24T12:00:00Z',
      },
      {
        status: 'shipped',
        detail: 'delivered',
        created_at: '2026-10-24T13:00:00Z',
      },
    ]);

    expect(groups).toHaveLength(2);
    expect(groups[0].events).toHaveLength(2);
    expect(groups[0].first_at).toBe('2026-10-24T10:00:00Z');
    expect(groups[0].last_at).toBe('2026-10-24T10:10:00Z');
    expect(groups[1].events).toHaveLength(2);
  });

  it('keeps separated occurrences of the same status in chronological order', () => {
    const groups = groupTrackingHistory([
      { status: 'shipped', detail: null, created_at: '2026-10-24T10:00:00Z' },
      { status: 'delivered', detail: null, created_at: '2026-10-24T11:00:00Z' },
      { status: 'shipped', detail: null, created_at: '2026-10-24T12:00:00Z' },
    ]);

    expect(groups.map((group) => group.label)).toEqual(['Em trânsito', 'Entregue', 'Em trânsito']);
  });

  it('does not merge equal statuses from different event types', () => {
    const groups = groupTrackingHistory(
      [
        {
          event_type: 'order_status',
          status: 'shipped',
          detail: null,
          created_at: '2026-10-24T10:00:00Z',
        },
        {
          event_type: 'shipment_status',
          status: 'shipped',
          detail: null,
          created_at: '2026-10-24T11:00:00Z',
        },
      ],
      true,
    );

    expect(groups).toHaveLength(2);
  });
});
