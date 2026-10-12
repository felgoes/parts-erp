import { Component, input } from '@angular/core';

@Component({
  selector: 'app-page-header',
  templateUrl: './page-header.html',
})
export class PageHeader {
  readonly eyebrow = input('Operação');
  readonly title = input.required<string>();
  readonly subtitle = input('');
}
