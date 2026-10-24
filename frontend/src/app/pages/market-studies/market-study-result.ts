import { CurrencyPipe, DatePipe } from '@angular/common';
import { Component, Input, ViewEncapsulation } from '@angular/core';
import { MarketStudy } from '../../core/models';

@Component({
  selector: 'app-market-study-result',
  standalone: true,
  imports: [CurrencyPipe, DatePipe],
  templateUrl: './market-study-result.html',
  styleUrl: './market-studies.scss',
  encapsulation: ViewEncapsulation.None,
})
export class MarketStudyResult {
  @Input({ required: true }) study!: MarketStudy;

  confidenceLabel(confidence: string | undefined): string {
    return confidence === 'high' ? 'alta' : confidence === 'medium' ? 'média' : 'baixa';
  }
}
