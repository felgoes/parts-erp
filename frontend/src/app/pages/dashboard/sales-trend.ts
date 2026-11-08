import { CurrencyPipe, DecimalPipe } from '@angular/common';
import { Component, computed, input, signal } from '@angular/core';
import { animate } from 'animejs/animation';
import { EntryMotion, type EntrySequence } from '../../shared/entry-motion';
import type { DashboardDailyMetric } from '../../core/models/dashboard';

const LEFT = 12;
const RIGHT = 988;
const TOP = 14;
const BOTTOM = 150;

@Component({
  selector: 'app-sales-trend',
  imports: [CurrencyPipe, DecimalPipe, EntryMotion],
  templateUrl: './sales-trend.html',
  styleUrl: './sales-trend.scss',
})
export class SalesTrend {
  readonly daily = input.required<DashboardDailyMetric[]>();
  readonly countOnly = input.required<boolean>();
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

  readonly draw: EntrySequence = (plot) => {
    const series = plot.querySelector<HTMLElement>('.trend-series-clip')!;
    const pen = plot.querySelector<HTMLElement>('.trend-pen')!;
    const progress = { value: 0 };
    const paint = () => {
      const points = this.points();
      if (!points.length) return;
      const cursor = progress.value * (points.length - 1);
      const before = points[Math.floor(cursor)];
      const after = points[Math.ceil(cursor)];
      const fraction = cursor % 1;
      const x = before.x + (after.x - before.x) * fraction;
      const y = before.y + (after.y - before.y) * fraction;
      series.style.clipPath = `inset(0 ${Math.max(0, 100 - x / 10 - .4)}% 0 0)`;
      pen.style.left = `${x / 10}%`;
      pen.style.top = `${y / 164 * 100}%`;
    };
    const showFinal = () => {
      series.style.removeProperty('clip-path');
      plot.classList.remove('is-drawing');
    };

    paint();
    plot.classList.add('is-drawing');
    const animation = animate(progress, {
      value: 1,
      delay: 170,
      duration: this.points().length > 1 ? 1450 : 480,
      ease: 'inOutSine',
      onRender: paint,
      onComplete: showFinal,
    });
    return () => {
      animation.cancel();
      showFinal();
    };
  };

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
