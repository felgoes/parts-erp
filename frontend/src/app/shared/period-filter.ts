import { Component, EventEmitter, Input, OnInit, Output } from '@angular/core';
import { FormsModule } from '@angular/forms';
import {
  DateRange,
  QUICK_DATE_PRESETS,
  QuickDatePreset,
  quickDateRange,
} from '../core/quick-date-ranges';

export interface PeriodFilterStatusOption {
  value: string;
  label: string;
  count: number;
}

@Component({
  selector: 'app-period-filter',
  imports: [FormsModule],
  styles: [':host { display: block; }'],
  templateUrl: './period-filter.html',
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
    const presetRange =
      this.initialPreset === 'custom'
        ? quickDateRange('thisMonth')
        : quickDateRange(this.initialPreset);
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
    if (this.validRange() && !this.busy)
      this.rangeChange.emit({ startDate: this.startDate, endDate: this.endDate });
  }
}
