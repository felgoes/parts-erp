import { DOCUMENT } from '@angular/common';
import { Injectable, inject, signal } from '@angular/core';

export type AppearanceTheme = 'light' | 'dark';

@Injectable({ providedIn: 'root' })
export class AppearanceService {
  private readonly document = inject(DOCUMENT);
  private readonly storageKey = 'parts-erp-theme';
  readonly theme = signal<AppearanceTheme>(this.restoreTheme());

  constructor() {
    this.apply(this.theme());
  }

  setTheme(theme: AppearanceTheme): void {
    this.theme.set(theme);
    localStorage.setItem(this.storageKey, theme);
    this.apply(theme);
  }

  private restoreTheme(): AppearanceTheme {
    try {
      return localStorage.getItem(this.storageKey) === 'dark' ? 'dark' : 'light';
    } catch {
      return 'light';
    }
  }

  private apply(theme: AppearanceTheme): void {
    this.document.body.dataset['theme'] = theme;
    this.document.documentElement.style.colorScheme = theme;
  }
}
