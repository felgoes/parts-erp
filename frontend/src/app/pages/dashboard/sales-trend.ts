import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, computed, effect, ElementRef, input, signal, viewChild } from '@angular/core';
import type { DashboardDailyMetric } from '../../core/models/dashboard';

const LEFT = 12;
const RIGHT = 988;
const TOP = 14;
const BOTTOM = 150;

@Component({
  selector: 'app-sales-trend',
  imports: [CurrencyPipe, DecimalPipe],
  templateUrl: './sales-trend.html',
  styleUrl: './sales-trend.scss',
})
export class SalesTrend {
  readonly daily = input.required<DashboardDailyMetric[]>();
  readonly countOnly = input.required<boolean>();
  private readonly plot = viewChild<ElementRef<HTMLElement>>('plot');
  readonly revealed = signal(false);
  private readonly chosenDate = signal<string | null>(null);
  readonly points = computed(() => {
    const days = this.daily();
    const values = days.map((day) => this.countOnly() ? day.count : Number(day.amount));
    const min = Math.min(0, ...values);
    const max = Math.max(0, ...values);
    const span = max - min || 1;
    return days.map((day, index) => ({
      ...day,
      x: days.length === 1 ? 500 : LEFT + (RIGHT - LEFT) * index / (days.length - 1),
      y: BOTTOM - (BOTTOM - TOP) * (values[index] - min) / span,
      baseline: BOTTOM + (BOTTOM - TOP) * min / span,
    }));
  });
  readonly hasSales = computed(() => this.daily().some((day) => day.count > 0));
  readonly line = computed(() => this.points().map(({ x, y }) => x + ',' + y).join(' '));
  readonly area = computed(() => {
    const points = this.points();
    const first = points[0];
    const last = points.at(-1);
    return first && last ? first.x + ',' + first.baseline + ' ' + this.line() + ' ' + last.x + ',' + last.baseline : '';
  });
  readonly selectedIndex = computed(() => {
    const days = this.daily();
    const chosen = days.findIndex((day) => day.date === this.chosenDate());
    if (chosen >= 0) return chosen;
    for (let index = days.length - 1; index >= 0; index--) {
      if (days[index].count > 0) return index;
    }
    return 0;
  });

  constructor() {
    effect((onCleanup) => {
      const plot = this.plot()?.nativeElement;
      if (!plot) {
        this.revealed.set(false);
        return;
      }
      if (this.revealed()) return;

      if (typeof IntersectionObserver === 'undefined') {
        this.revealed.set(true);
        return;
      }
      const threshold = .25;
      const observer = new IntersectionObserver((entries) => {
        if (entries.some((entry) => entry.intersectionRatio >= threshold)) this.revealed.set(true);
      }, { threshold });
      observer.observe(plot);
      onCleanup(() => observer.disconnect());
    });
  }

  selectIndex(index: number) {
    const day = this.daily()[index];
    if (day) this.chosenDate.set(day.date);
  }

  selectPoint(event: PointerEvent) {
    if (event.type === 'pointermove' && event.pointerType !== 'mouse') return;
    const bounds = (event.currentTarget as HTMLElement).getBoundingClientRect();
    if (!bounds.width) return;
    const fraction = ((event.clientX - bounds.left) / bounds.width * 1000 - LEFT) / (RIGHT - LEFT);
    const last = this.daily().length - 1;
    this.selectIndex(Math.max(0, Math.min(last, Math.round(fraction * last))));
  }
}
