import { Component, input } from '@angular/core';

@Component({
  selector: 'app-page-header',
  template: `<header class="page-header">
    <div>
      <p class="eyebrow">{{ eyebrow() }}</p>
      <h1>{{ title() }}</h1>
      <p class="subtitle">{{ subtitle() }}</p>
    </div>
    <ng-content />
  </header>`,
})
export class PageHeader {
  readonly eyebrow = input('Operação');
  readonly title = input.required<string>();
  readonly subtitle = input('');
}
