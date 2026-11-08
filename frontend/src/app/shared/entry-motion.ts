import { Directive, ElementRef, NgZone, afterRenderEffect, inject, input } from '@angular/core';

export type EntrySequence = (element: HTMLElement) => () => void;

@Directive({
  selector: '[appEntryMotion]',
  host: { 'data-entry-motion': 'waiting' },
})
export class EntryMotion {
  readonly appEntryMotion = input.required<EntrySequence>();
  readonly entryMotionKey = input<string>();
  private readonly element = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
  private readonly zone = inject(NgZone);

  constructor() {
    afterRenderEffect({
      write: (onCleanup) => {
        const play = this.appEntryMotion();
        this.entryMotionKey();
        onCleanup(this.zone.runOutsideAngular(() => this.observe(play)));
      },
    });
  }

  private observe(play: EntrySequence): () => void {
    const element = this.element;
    const document = element.ownerDocument;
    const view = document.defaultView;
    if (!view) return () => {};

    const preference = view.matchMedia('(prefers-reduced-motion: reduce)');
    let inView = typeof IntersectionObserver === 'undefined';
    let pending = true;
    let stop: (() => void) | undefined;

    const start = () => {
      if (!pending || !inView || document.visibilityState !== 'visible') return;
      pending = false;
      if (!preference.matches) stop = play(element);
      element.dataset['entryMotion'] = 'ready';
    };
    const reset = () => {
      stop?.();
      stop = undefined;
      pending = !preference.matches;
      element.dataset['entryMotion'] = pending ? 'waiting' : 'ready';
      start();
    };

    const observer = typeof IntersectionObserver === 'undefined' ? undefined : new IntersectionObserver((entries) => {
      inView = (entries.at(-1)?.intersectionRatio ?? 0) >= .2;
      start();
    }, { threshold: .2 });
    const restore = (event: PageTransitionEvent) => {
      if (!event.persisted) return;
      inView = !observer;
      observer?.disconnect();
      observer?.observe(element);
      reset();
    };
    const reduce = () => {
      if (preference.matches) reset();
    };

    observer?.observe(element);
    document.addEventListener('visibilitychange', start);
    view.addEventListener('pageshow', restore);
    preference.addEventListener('change', reduce);
    reset();

    return () => {
      observer?.disconnect();
      document.removeEventListener('visibilitychange', start);
      view.removeEventListener('pageshow', restore);
      preference.removeEventListener('change', reduce);
      stop?.();
    };
  }
}
