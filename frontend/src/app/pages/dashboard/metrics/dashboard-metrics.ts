import { CurrencyPipe } from '@angular/common';
import { Component, input, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DashboardSummary } from '../../../core/models';

@Component({
  selector: 'app-dashboard-metrics',
  imports: [CurrencyPipe, RouterLink],
  templateUrl: './dashboard-metrics.html',
  styleUrl: './dashboard-metrics.scss',
})
export class DashboardMetrics {
  readonly summary = input.required<DashboardSummary>();
  readonly financialRequested = output<void>();
}
