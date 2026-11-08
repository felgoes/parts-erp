import { DestroyRef, Directive, ElementRef, NgZone, inject, signal } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs';

export interface HeaderScrollState {
  pivot: number;
  hidden: boolean;
}

export function trackHeaderScroll(state: HeaderScrollState, offset: number, headerHeight: number): HeaderScrollState {
  if (offset <= 12) return { pivot: offset, hidden: false };
  if (state.hidden) {
    if (state.pivot - offset >= 12) return { pivot: offset, hidden: false };
    return { pivot: Math.max(offset, state.pivot), hidden: true };
  }
  if (offset >= headerHeight && offset - state.pivot >= 18) return { pivot: offset, hidden: true };
  return { pivot: Math.min(offset, state.pivot), hidden: false };
}

@Directive({
  selector: '[appScrollHeader]',
  host: { '[class.is-scroll-hidden]': 'hidden()' },
})
export class ScrollHeader {
  readonly hidden = signal(false);

  constructor() {
    const header = inject<ElementRef<HTMLElement>>(ElementRef).nativeElement;
    const destroy = inject(DestroyRef);
    const router = inject(Router);
    const zone = inject(NgZone);
    const mobile = window.matchMedia('(width < 768px)');
    let frame: number | null = null;
    const offset = () => {
      const page = document.scrollingElement;
      const limit = page ? Math.max(0, page.scrollHeight - page.clientHeight) : Infinity;
      return Math.min(limit, Math.max(0, window.scrollY));
    };
    let state: HeaderScrollState = { pivot: offset(), hidden: false };
    const reset = () => {
      if (frame !== null) window.cancelAnimationFrame(frame);
      frame = null;
      state = { pivot: offset(), hidden: false };
      this.hidden.set(false);
    };
    const scroll = () => {
      if (!mobile.matches || frame !== null) return;
      frame = window.requestAnimationFrame(() => {
        frame = null;
        state = trackHeaderScroll(state, offset(), header.offsetHeight);
        if (this.hidden() !== state.hidden) this.hidden.set(state.hidden);
      });
    };

    zone.runOutsideAngular(() => {
      window.addEventListener('scroll', scroll, { passive: true });
      mobile.addEventListener('change', reset);
    });
    router.events.pipe(filter(event => event instanceof NavigationEnd), takeUntilDestroyed(destroy)).subscribe(reset);
    destroy.onDestroy(() => {
      window.removeEventListener('scroll', scroll);
      mobile.removeEventListener('change', reset);
      if (frame !== null) window.cancelAnimationFrame(frame);
    });
  }
}
