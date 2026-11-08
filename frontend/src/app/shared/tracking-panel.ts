import { DatePipe } from '@angular/common';
import { Component, input } from '@angular/core';
import type { InvoiceTracking } from '../core/models/invoices';
import { statusLabel, trackingEventLabel } from '../core/status-labels';
import { ShippingRouteMap } from './shipping-route-map';
import { TrackingTimeline } from './tracking-timeline';

@Component({
  selector: 'app-tracking-panel',
  imports: [DatePipe, ShippingRouteMap, TrackingTimeline],
  templateUrl: './tracking-panel.html',
  styleUrl: './tracking-panel.scss',
})
export class TrackingPanel {
  readonly tracking = input.required<InvoiceTracking>();
  readonly statusLabel = statusLabel;
  readonly trackingEventLabel = trackingEventLabel;
}
