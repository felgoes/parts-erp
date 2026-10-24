import { DatePipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';
import { TrackingHistoryEvent, groupTrackingHistory } from '../core/tracking-history';
import { trackingEventLabel } from '../core/status-labels';

@Component({
  selector: 'app-tracking-timeline',
  imports: [DatePipe],
  templateUrl: './tracking-timeline.html',
  styleUrl: './tracking-timeline.scss',
})
export class TrackingTimeline {
  readonly events = input.required<readonly TrackingHistoryEvent[]>();
  readonly groupByEventType = input(false);
  readonly historyGroups = computed(() =>
    groupTrackingHistory(this.events(), this.groupByEventType()),
  );
  readonly trackingEventLabel = trackingEventLabel;
}
