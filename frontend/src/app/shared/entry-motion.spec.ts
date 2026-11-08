import { Component, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { EntryMotion } from './entry-motion';

@Component({
  imports: [EntryMotion],
  template: '<div [appEntryMotion]="play" [entryMotionKey]="sale()" [attr.data-status]="status()"></div>',
})
class RecordHost {
  readonly sale = signal('sale-one');
  readonly status = signal('shipped');
  readonly stop = vi.fn();
  readonly play = vi.fn(() => this.stop);
}

describe('EntryMotion', () => {
  let reportVisibility: (ratio: number) => void;
  let reduced: boolean;
  let visibility: DocumentVisibilityState;

  beforeEach(() => {
    reduced = false;
    visibility = 'visible';
    vi.stubGlobal('IntersectionObserver', class {
      constructor(callback: IntersectionObserverCallback) {
        reportVisibility = (intersectionRatio) => callback([{ intersectionRatio } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
      }
      observe() {}
      disconnect() {}
    });
    vi.stubGlobal('matchMedia', () => ({
      matches: reduced,
      addEventListener() {},
      removeEventListener() {},
    }));
    vi.spyOn(document, 'visibilityState', 'get').mockImplementation(() => visibility);
  });

  afterEach(() => {
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it('waits until visible and plays again for a different record, without replaying a status refresh', async () => {
    visibility = 'hidden';
    const fixture = TestBed.createComponent(RecordHost);
    const host = fixture.componentInstance;
    await fixture.whenStable();

    reportVisibility(.1);
    expect(host.play).not.toHaveBeenCalled();
    reportVisibility(.6);
    expect(host.play).not.toHaveBeenCalled();

    visibility = 'visible';
    document.dispatchEvent(new Event('visibilitychange'));
    expect(host.play).toHaveBeenCalledTimes(1);

    host.status.set('delivered');
    await fixture.whenStable();
    reportVisibility(0);
    reportVisibility(.6);
    expect(host.play).toHaveBeenCalledTimes(1);

    host.sale.set('sale-two');
    await fixture.whenStable();
    expect(host.stop).toHaveBeenCalledTimes(1);
    reportVisibility(.6);
    expect(host.play).toHaveBeenCalledTimes(2);
    fixture.destroy();
    expect(host.stop).toHaveBeenCalledTimes(2);
  });

  it('immediately shows the final state when the device prefers reduced motion', async () => {
    reduced = true;
    const fixture = TestBed.createComponent(RecordHost);
    await fixture.whenStable();
    expect(fixture.nativeElement.querySelector('[data-entry-motion]').getAttribute('data-entry-motion')).toBe('ready');
    reportVisibility(1);
    expect(fixture.componentInstance.play).not.toHaveBeenCalled();
  });
});
