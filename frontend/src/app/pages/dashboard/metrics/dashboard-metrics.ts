import { CurrencyPipe } from '@angular/common';
import { Component, input, output } from '@angular/core';
import { DashboardSummary } from '../../../core/models';
import { DashboardMetricCard } from './dashboard-metric-card';

@Component({
  selector: 'app-dashboard-metrics',
  imports: [CurrencyPipe, DashboardMetricCard],
  templateUrl: './dashboard-metrics.html',
  styleUrl: './dashboard-metrics.scss',
})
export class DashboardMetrics {
  readonly summary = input.required<DashboardSummary>();
  readonly financialRequested = output<void>();
}
