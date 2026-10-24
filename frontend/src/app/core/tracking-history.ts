import { trackingEventLabel } from './status-labels';

export interface TrackingHistoryEvent {
  status: string;
  detail: string | null;
  created_at: string;
  event_type?: string;
}

export interface TrackingHistoryGroup<T extends TrackingHistoryEvent = TrackingHistoryEvent> {
  key: string;
  label: string;
  first_at: string;
  last_at: string;
  events: T[];
}

export function groupTrackingHistory<T extends TrackingHistoryEvent>(
  events: readonly T[],
  groupByEventType = false,
): TrackingHistoryGroup<T>[] {
  const groups: TrackingHistoryGroup<T>[] = [];
  for (const event of events) {
    const statusKey = historyKey(event, groupByEventType);
    const current = groups.at(-1);
    const currentKey = current ? historyKey(current.events[0], groupByEventType) : null;
    if (!current || currentKey !== statusKey) {
      groups.push({
        key: `${statusKey}-${groups.length}`,
        label: trackingEventLabel(event.status, event.detail),
        first_at: event.created_at,
        last_at: event.created_at,
        events: [event],
      });
      continue;
    }
    current.events.push(event);
    current.label = trackingEventLabel(event.status, event.detail);
    current.last_at = event.created_at;
  }
  return groups;
}

function historyKey(event: TrackingHistoryEvent, groupByEventType: boolean): string {
  return [
    groupByEventType ? event.event_type || '' : '',
    normalizeTrackingStatus(event.status),
  ].join(':');
}

function normalizeTrackingStatus(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[.\s-]+/g, '_')
    .replace(/_+/g, '_');
}
