import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DateRange, QUICK_DATE_PRESETS, QuickDatePreset, quickDateRange } from '../core/quick-date-ranges';

export interface PeriodFilterStatusOption {
  value: string;
  label: string;
  count: number;
}

@Component({
  selector: 'app-period-filter',
  imports: [FormsModule],
  styles: [':host { display: block; }'],
  template: `
    <section
      class="date-filter card shared-period-filter"
      [class.invoice-filter-toolbar]="statusOptions.length > 0"
      [class.has-custom-range]="activePreset === 'custom'"
      [attr.aria-label]="ariaLabel"
    >
      <div class="date-filter-heading">
        <strong>{{ heading }}</strong>
        @if (description) { <small>{{ description }}</small> }
      </div>

      @if (statusOptions.length) {
        <div class="date-filter-options">
          <div class="date-quick-filters" role="group" aria-label="Atalhos de período">
            @for (preset of datePresets; track preset.id) {
              <button type="button" class="date-preset" [class.active]="activePreset === preset.id" [attr.aria-pressed]="activePreset === preset.id" (click)="selectPreset(preset.id)">{{ preset.label }}</button>
            }
          </div>
          <div class="invoice-status-filter" role="group" aria-label="Filtrar por situação">
            <span>Situação</span>
            @for (option of statusOptions; track option.value) {
              <button type="button" [class.active]="selectedStatus === option.value" [attr.aria-pressed]="selectedStatus === option.value" (click)="selectStatus(option.value)">{{ option.label }} <small>{{ option.count }}</small></button>
            }
          </div>
        </div>
      } @else {
        <div class="date-quick-filters" role="group" aria-label="Atalhos de período">
          @for (preset of datePresets; track preset.id) {
            <button type="button" class="date-preset" [class.active]="activePreset === preset.id" [attr.aria-pressed]="activePreset === preset.id" (click)="selectPreset(preset.id)">{{ preset.label }}</button>
          }
        </div>
      }

      @if (activePreset === 'custom') {
        <div class="date-range-fields">
          <label>De <input type="date" [ngModel]="startDate" (ngModelChange)="changeStart($event)" /></label>
          <label>Até <input type="date" [ngModel]="endDate" (ngModelChange)="changeEnd($event)" /></label>
          <button class="secondary" type="button" (click)="applyRange()" [disabled]="busy || !validRange()">{{ busy ? 'Atualizando…' : applyLabel }}</button>
        </div>
      }
    </section>
  `,
})
export class PeriodFilter implements OnInit {
  @Input() heading = 'Período';
  @Input() description = '';
  @Input() ariaLabel = 'Filtrar por período';
  @Input() initialPreset: QuickDatePreset = 'thisMonth';
  @Input() initialStartDate = '';
  @Input() initialEndDate = '';
  @Input() applyLabel = 'Aplicar período';
  @Input() busy = false;
  @Input() statusOptions: PeriodFilterStatusOption[] = [];
  @Input() selectedStatus = 'all';

  @Output() rangeChange = new EventEmitter<DateRange>();
  @Output() statusChange = new EventEmitter<string>();

  readonly datePresets = QUICK_DATE_PRESETS;
  activePreset: QuickDatePreset = 'thisMonth';
  startDate = '';
  endDate = '';

  ngOnInit() {
    this.activePreset = this.initialPreset;
    const presetRange = this.initialPreset === 'custom' ? quickDateRange('thisMonth') : quickDateRange(this.initialPreset);
    this.startDate = this.initialStartDate || presetRange.startDate;
    this.endDate = this.initialEndDate || presetRange.endDate;
  }

  selectPreset(preset: QuickDatePreset) {
    this.activePreset = preset;
    if (preset === 'custom') return;
    const range = quickDateRange(preset);
    this.startDate = range.startDate;
    this.endDate = range.endDate;
    this.rangeChange.emit(range);
  }

  changeStart(value: string) {
    this.startDate = value;
    this.activePreset = 'custom';
  }

  changeEnd(value: string) {
    this.endDate = value;
    this.activePreset = 'custom';
  }

  selectStatus(status: string) {
    this.selectedStatus = status;
    this.statusChange.emit(status);
  }

  validRange() {
    return !!this.startDate && !!this.endDate && this.startDate <= this.endDate;
  }

  applyRange() {
    if (this.validRange() && !this.busy) this.rangeChange.emit({ startDate: this.startDate, endDate: this.endDate });
  }
}
