export interface RecordOrigin {
  path: string;
  label: string;
  focusId?: string;
  scrollY?: number;
  view?: unknown;
}

export function recordOrigin(
  currentUrl: string,
  label: string,
  focusId?: string,
  view?: unknown,
): { recordOrigin: RecordOrigin } {
  const origin = { path: currentUrl, label, focusId, scrollY: window.scrollY, view };
  window.history.replaceState({ ...window.history.state, recordReturn: origin }, '');
  return { recordOrigin: origin };
}

export function readRecordOrigin(allowed: Readonly<Record<string, string>>, fallback: string): RecordOrigin {
  const candidate = window.history.state?.recordOrigin as RecordOrigin | undefined;
  const base = typeof candidate?.path === 'string' ? candidate.path.split(/[?#]/)[0] : '';
  const label = Object.hasOwn(allowed, base) ? allowed[base] : undefined;
  return candidate && label ? { ...candidate, label } : { path: fallback, label: allowed[fallback] };
}

export function restoreRecordPosition(origin: RecordOrigin | undefined): void {
  if (!origin) return;
  requestAnimationFrame(() => {
    if (Number.isFinite(origin.scrollY)) window.scrollTo(0, origin.scrollY!);
    if (typeof origin.focusId !== 'string') return;
    const targets = Array.from(document.querySelectorAll<HTMLElement>('[data-record-focus]'));
    targets.find((target) =>
      target.dataset['recordFocus'] === origin.focusId && target.getClientRects().length,
    )?.focus({ preventScroll: true });
  });
}
