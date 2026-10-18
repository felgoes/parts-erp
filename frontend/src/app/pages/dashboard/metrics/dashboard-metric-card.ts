import { Component, input } from '@angular/core';
import { RouterLink } from '@angular/router';

export type DashboardMetricTone = 'neutral' | 'positive' | 'attention';

@Component({
  selector: 'app-dashboard-metric-card',
  imports: [RouterLink],
  templateUrl: './dashboard-metric-card.html',
  styleUrl: './dashboard-metric-card.scss',
})
export class DashboardMetricCard {
  readonly label = input.required<string>();
  readonly value = input.required<string>();
  readonly meta = input('');
  readonly detail = input('');
  readonly iconPath = input.required<string>();
  readonly route = input.required<string>();
  readonly tone = input<DashboardMetricTone>('neutral');
}
