import { NgTemplateOutlet } from '@angular/common';
import { Component, ElementRef, EventEmitter, inject, Input, OnInit, Output, ViewChild } from '@angular/core';
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
  imports: [FormsModule, NgTemplateOutlet],
  styleUrl: './period-filter.scss',
  host: {
    '(document:pointerdown)': 'dismissOutside($event.target)',
    '(focusout)': 'dismissOutside($event.relatedTarget)',
    '(keydown.escape)': 'escapePicker($event)',
  },
  templateUrl: './period-filter.html',
})
export class PeriodFilter implements OnInit {
  @Input() compact = false;
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

  private static nextPickerId = 0;
  private readonly hostElement = inject(ElementRef<HTMLElement>);
  @ViewChild('pickerTrigger') private pickerTrigger?: ElementRef<HTMLButtonElement>;

  readonly pickerId = `period-picker-${++PeriodFilter.nextPickerId}`;
  pickerOpen = false;
  customDraft: DateRange | null = null;

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

  get presetLabel() {
    return this.datePresets.find(({ id }) => id === this.activePreset)?.label;
  }

  togglePicker() {
    if (this.pickerOpen) this.closePicker();
    else {
      this.pickerOpen = true;
      if (this.activePreset === 'custom') this.startCustomDraft();
    }
  }

  choosePreset(preset: QuickDatePreset) {
    if (preset === 'custom') {
      this.startCustomDraft();
      return;
    }
    this.selectPreset(preset);
    this.closePicker(true);
  }

  private startCustomDraft() {
    this.customDraft ??= { startDate: this.startDate, endDate: this.endDate };
  }

  dismissOutside(target: EventTarget | null) {
    if (this.pickerOpen && target instanceof Node && !this.hostElement.nativeElement.contains(target))
      this.closePicker();
  }

  escapePicker(event: Event) {
    if (!this.pickerOpen || event.defaultPrevented) return;
    event.preventDefault();
    event.stopPropagation();
    this.closePicker(true);
  }

  private closePicker(restoreFocus = false) {
    this.pickerOpen = false;
    this.customDraft = null;
    if (restoreFocus) this.pickerTrigger?.nativeElement.focus();
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
    if (this.customDraft) {
      this.customDraft.startDate = value;
      return;
    }
    this.startDate = value;
    this.activePreset = 'custom';
  }

  changeEnd(value: string) {
    if (this.customDraft) {
      this.customDraft.endDate = value;
      return;
    }
    this.endDate = value;
    this.activePreset = 'custom';
  }

  selectStatus(status: string) {
    this.selectedStatus = status;
    this.statusChange.emit(status);
  }

  validRange() {
    const { startDate, endDate } = this.customDraft ?? this;
    return !!startDate && !!endDate && startDate <= endDate;
  }

  applyRange() {
    if (!this.validRange() || this.busy) return;
    if (this.customDraft) {
      this.activePreset = 'custom';
      ({ startDate: this.startDate, endDate: this.endDate } = this.customDraft);
      this.closePicker(true);
    }
    this.rangeChange.emit({ startDate: this.startDate, endDate: this.endDate });
  }
}
