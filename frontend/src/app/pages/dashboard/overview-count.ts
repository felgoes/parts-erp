import { Component, LOCALE_ID, computed, inject, input } from '@angular/core';
import { animate } from 'animejs/animation';
import { EntryMotion, type EntrySequence } from '../../shared/entry-motion';

@Component({
  selector: 'app-overview-count',
  imports: [EntryMotion],
  template: `
    <span class="counter" [appEntryMotion]="countUp">
      <span class="counter-value">{{ formatted() }}</span>
      <span class="counter-frame" aria-hidden="true">{{ initial() }}</span>
    </span>
  `,
  styles: `
    .counter {
      display: inline-grid;
      max-inline-size: 100%;
      align-items: start;
      vertical-align: baseline;
      font-variant-numeric: tabular-nums;
    }
    .counter-value, .counter-frame { grid-area: 1 / 1; }
    .counter-frame { visibility: hidden; contain: inline-size; pointer-events: none; }
    @media (prefers-reduced-motion: no-preference) {
      .counter:is([data-entry-motion='waiting'], .is-counting) .counter-value { opacity: 0; }
      .counter:is([data-entry-motion='waiting'], .is-counting) .counter-frame { visibility: visible; }
    }
  `,
})
export class OverviewCount {
  readonly value = input.required<number | string>();
  readonly currency = input(false);
  readonly units = input<readonly [singular: string, plural: string]>();
  private readonly locale = inject(LOCALE_ID);
  private readonly formatter = computed(() => new Intl.NumberFormat(this.locale, this.currency()
    ? { style: 'currency', currency: 'BRL' }
    : { maximumFractionDigits: 0 }));
  readonly formatted = computed(() => this.format(Number(this.value())));
  readonly initial = computed(() => this.format(0));

  private format(value: number): string {
    const units = this.units();
    const number = this.formatter().format(value);
    return units ? number + ' ' + units[value === 1 ? 0 : 1] : number;
  }

  readonly countUp: EntrySequence = (element) => {
    const frame = element.querySelector<HTMLElement>('.counter-frame')!;
    const progress = { value: 0 };
    const factor = this.currency() ? 100 : 1;
    const paint = () => {
      const current = Math.round(Number(this.value()) * progress.value * factor) / factor || 0;
      const text = this.format(current);
      if (frame.textContent !== text) frame.textContent = text;
    };
    const finish = () => {
      element.classList.remove('is-counting');
      frame.textContent = this.initial();
    };

    if (!Number(this.value())) return () => {};
    paint();
    element.classList.add('is-counting');
    const animation = animate(progress, {
      value: 1,
      delay: 130,
      duration: this.currency() ? 1100 : 740,
      ease: 'outCubic',
      onRender: paint,
      onComplete: finish,
    });
    return () => {
      animation.cancel();
      finish();
    };
  };
}
