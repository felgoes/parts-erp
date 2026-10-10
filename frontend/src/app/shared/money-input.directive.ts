import { Directive, ElementRef, EventEmitter, HostListener, Input, OnChanges, Output, SimpleChanges, forwardRef, inject } from '@angular/core';
import { AbstractControl, ControlValueAccessor, NG_VALIDATORS, NG_VALUE_ACCESSOR, ValidationErrors, Validator } from '@angular/forms';

type ParsedMoney = { value: number | null; cents: number | null; valid: boolean; incomplete: boolean };

@Directive({
  selector: 'input[appMoneyInput]',
  standalone: true,
  providers: [
    { provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => MoneyInputDirective), multi: true },
    { provide: NG_VALIDATORS, useExisting: forwardRef(() => MoneyInputDirective), multi: true },
  ],
  host: { '[attr.type]': '"text"', '[attr.inputmode]': '"decimal"', '[attr.autocomplete]': '"off"' },
})
export class MoneyInputDirective implements ControlValueAccessor, Validator, OnChanges {
  @Input() appMoneyInput: number | string | null | undefined;
  @Output() moneyInput = new EventEmitter<number | null>();
  @Output() moneyValidity = new EventEmitter<boolean>();

  private readonly element = inject(ElementRef<HTMLInputElement>);
  private onChange: (value: number | null) => void = () => undefined;
  private onTouched: () => void = () => undefined;
  private validatorChanged: () => void = () => undefined;
  private rawValue = '';
  private formatError = false;
  private focused = false;
  private hint?: HTMLElement;

  ngOnChanges(changes: SimpleChanges) {
    if (changes['appMoneyInput'] && !this.focused && (typeof this.appMoneyInput === 'number' || this.appMoneyInput === null)) {
      this.rawValue = this.appMoneyInput === null ? '' : this.formatInputValue(this.appMoneyInput);
      this.element.nativeElement.value = this.rawValue;
      this.setValidity();
      this.validatorChanged();
      this.moneyValidity.emit(this.formatError);
    }
  }

  writeValue(value: number | string | null | undefined): void {
    if (this.focused || this.formatError) return;
    const numeric = value === null || value === undefined || value === '' ? null : Number(value);
    this.rawValue = numeric === null || !Number.isFinite(numeric) ? '' : this.formatInputValue(numeric);
    this.element.nativeElement.value = this.rawValue;
    this.setValidity();
    this.validatorChanged();
    this.moneyValidity.emit(this.formatError);
  }

  registerOnChange(fn: (value: number | null) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = fn; }
  setDisabledState(disabled: boolean): void { this.element.nativeElement.disabled = disabled; }
  registerOnValidatorChange(fn: () => void): void { this.validatorChanged = fn; }

  validate(_control: AbstractControl): ValidationErrors | null {
    if (this.formatError) return { moneyFormat: { message: this.message() } };
    const parsed = this.parse(this.rawValue);
    const minAttribute = this.element.nativeElement.getAttribute('min');
    const maxAttribute = this.element.nativeElement.getAttribute('max');
    const min = minAttribute === null ? Number.NaN : Number(minAttribute);
    const max = maxAttribute === null ? Number.NaN : Number(maxAttribute);
    if (parsed.value !== null && Number.isFinite(min) && parsed.value < min) return { min: { min, actual: parsed.value } };
    if (parsed.value !== null && Number.isFinite(max) && parsed.value > max) return { max: { max, actual: parsed.value } };
    return null;
  }

  @HostListener('focus') onFocus() {
    this.focused = true;
    const input = this.element.nativeElement;
    const caret = input.selectionStart ?? input.value.length;
    const digitsBeforeCaret = (input.value.slice(0, caret).match(/[0-9]/g) || []).length;
    const parsed = this.parse(input.value);
    if (!parsed.valid || parsed.cents === null) return;

    const cents = Math.abs(parsed.cents);
    const whole = Math.floor(cents / 100).toString();
    const decimals = String(cents % 100).padStart(2, '0');
    const editable = `${parsed.cents < 0 ? '-' : ''}${whole},${decimals}`;
    this.rawValue = editable;
    input.value = editable;
    if (parsed.cents === 0) input.setSelectionRange(0, input.value.length);
    else this.setCaretAfterDigitCount(input, digitsBeforeCaret);
  }

  @HostListener('input') onInput() {
    const input = this.element.nativeElement;
    const before = input.value;
    this.rawValue = before;
    const parsed = this.parse(before);
    const minAttribute = input.getAttribute('min');
    const maxAttribute = input.getAttribute('max');
    const min = minAttribute === null ? Number.NaN : Number(minAttribute);
    const max = maxAttribute === null ? Number.NaN : Number(maxAttribute);
    this.formatError = !parsed.valid || (parsed.value !== null && Number.isFinite(min) && parsed.value < min) || (parsed.value !== null && Number.isFinite(max) && parsed.value > max);

    if (parsed.valid) {
      this.onChange(parsed.value);
      this.moneyInput.emit(parsed.value);
    } else if (!parsed.valid) {
      this.onChange(null);
      this.moneyInput.emit(null);
    }

    this.setValidity();
    this.validatorChanged();
    this.moneyValidity.emit(this.formatError);
  }

  @HostListener('blur') onBlur() {
    this.focused = false;
    const parsed = this.parse(this.rawValue);
    const minAttribute = this.element.nativeElement.getAttribute('min');
    const maxAttribute = this.element.nativeElement.getAttribute('max');
    const min = minAttribute === null ? Number.NaN : Number(minAttribute);
    const max = maxAttribute === null ? Number.NaN : Number(maxAttribute);
    this.formatError = !parsed.valid || (parsed.value !== null && Number.isFinite(min) && parsed.value < min) || (parsed.value !== null && Number.isFinite(max) && parsed.value > max);
    if (parsed.valid && !this.formatError) {
      this.rawValue = parsed.value === null ? '' : this.format(parsed.value);
      this.element.nativeElement.value = this.rawValue;
      this.onChange(parsed.value);
      this.moneyInput.emit(parsed.value);
    }
    this.onTouched();
    this.setValidity();
    this.validatorChanged();
    this.moneyValidity.emit(this.formatError);
  }

  private parse(source: string): ParsedMoney {
    let text = source.replace(/\s/g, '').replace(/^R\$/i, '');
    if (!text) return { value: null, cents: null, valid: true, incomplete: false };
    const negative = text.startsWith('-');
    if (negative) text = text.slice(1);
    if (!text || (!/^\d+(?:,\d*)?$/.test(text) && !/^\d{1,3}(?:\.\d{3})+(?:,\d*)?$/.test(text))) {
      return { value: null, cents: null, valid: false, incomplete: false };
    }
    const comma = text.indexOf(',');
    const decimals = comma < 0 ? '' : text.slice(comma + 1);
    if (decimals.length > 2) return { value: null, cents: null, valid: false, incomplete: false };
    const incomplete = comma >= 0 && decimals.length === 0;
    const integerText = (comma < 0 ? text : text.slice(0, comma)).replace(/\./g, '');
    const cents = Number(integerText || '0') * 100 + Number((decimals + '00').slice(0, 2));
    const signedCents = negative ? -cents : cents;
    return { value: signedCents / 100, cents: signedCents, valid: true, incomplete };
  }

  private setCaretAfterDigitCount(input: HTMLInputElement, digitsBeforeCaret: number) {
    if (digitsBeforeCaret <= 0) {
      input.setSelectionRange(0, 0);
      return;
    }
    let seen = 0;
    for (let i = 0; i < input.value.length; i++) {
      if (/\d/.test(input.value[i])) seen++;
      if (seen >= digitsBeforeCaret) {
        input.setSelectionRange(i + 1, i + 1);
        return;
      }
    }
    input.setSelectionRange(input.value.length, input.value.length);
  }

  private format(value: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
  }

  private formatInputValue(value: number): string {
    const hasLegacyPrecision = Math.abs(value * 100 - Math.round(value * 100)) > 1e-8;
    this.formatError = hasLegacyPrecision;
    if (hasLegacyPrecision) {
      const decimals = Math.min(8, Math.max(3, (String(value).split('.')[1] || '').length));
      return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);
    }
    return this.format(value);
  }

  private message() { return 'Use reais com vírgula e no máximo duas casas decimais.'; }
  private setValidity() {
    const input = this.element.nativeElement;
    input.setCustomValidity(this.formatError ? this.message() : '');
    if (!this.hint) {
      this.hint = document.createElement('small');
      this.hint.className = 'money-input-error';
      this.hint.setAttribute('role', 'alert');
      input.insertAdjacentElement('afterend', this.hint);
    }
    if (this.formatError) {
      input.setAttribute('aria-invalid', 'true');
      this.hint.textContent = this.message();
      this.hint.removeAttribute('hidden');
    } else {
      input.removeAttribute('aria-invalid');
      this.hint.setAttribute('hidden', '');
      this.hint.textContent = '';
    }
  }
}
