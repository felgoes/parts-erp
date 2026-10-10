import { Directive, ElementRef, EventEmitter, HostListener, Input, OnChanges, Output, SimpleChanges, forwardRef, inject } from '@angular/core';
import { AbstractControl, ControlValueAccessor, NG_VALIDATORS, NG_VALUE_ACCESSOR, ValidationErrors, Validator } from '@angular/forms';

/** Limite de dígitos aceitos para o valor em centavos. */
const MAX_DIGITS = 15;

/**
 * Máscara de valores em reais "somente inclusão" (P10).
 *
 * O campo exibe sempre o formato completo — `R$ 1.234,56` — inclusive durante a digitação.
 * Digitar acrescenta um dígito no fim, então o valor cresce em centavos (`1` → `R$ 0,01`,
 * `1234` → `R$ 12,34`), e apagar remove só o último dígito. A vírgula, o ponto de milhar,
 * o `R$` e os zeros dos centavos nunca saem do lugar: não existe estado parcial nem
 * terceira casa decimal alcançável pelo teclado.
 *
 * Campo opcional sem valor continua em branco: vazio é "não informado" e é diferente de
 * `R$ 0,00`, que só aparece quando o valor é genuinamente zero.
 */
@Directive({
  selector: 'input[appMoneyInput]',
  standalone: true,
  providers: [
    { provide: NG_VALUE_ACCESSOR, useExisting: forwardRef(() => MoneyInputDirective), multi: true },
    { provide: NG_VALIDATORS, useExisting: forwardRef(() => MoneyInputDirective), multi: true },
  ],
  host: { '[attr.type]': '"text"', '[attr.inputmode]': '"numeric"', '[attr.autocomplete]': '"off"' },
})
export class MoneyInputDirective implements ControlValueAccessor, Validator, OnChanges {
  @Input() appMoneyInput: number | string | null | undefined;
  @Output() moneyInput = new EventEmitter<number | null>();
  @Output() moneyValidity = new EventEmitter<boolean>();

  private readonly element = inject(ElementRef<HTMLInputElement>);
  private onChange: (value: number | null) => void = () => undefined;
  private onTouched: () => void = () => undefined;
  private validatorChanged: () => void = () => undefined;
  /** Dígitos em centavos, sem zeros à esquerda. Vazio é "não informado". */
  private digits = '';
  private negative = false;
  /** Texto do valor legado com mais de duas casas, exibido até o usuário reescrever. */
  private legacyText: string | null = null;
  /** Campo opcional que entrou em foco sem valor volta a ficar em branco quando esvaziado. */
  private blankWhenCleared = false;
  private formatError = false;
  private focused = false;
  private hint?: HTMLElement;

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['appMoneyInput'] && !this.focused && this.appMoneyInput !== undefined) {
      this.applyIncoming(this.toNumber(this.appMoneyInput));
    }
  }

  writeValue(value: number | string | null | undefined): void {
    if (this.focused) return;
    this.applyIncoming(this.toNumber(value));
  }

  registerOnChange(fn: (value: number | null) => void): void { this.onChange = fn; }
  registerOnTouched(fn: () => void): void { this.onTouched = fn; }
  setDisabledState(disabled: boolean): void { this.element.nativeElement.disabled = disabled; }
  registerOnValidatorChange(fn: () => void): void { this.validatorChanged = fn; }

  validate(_control: AbstractControl): ValidationErrors | null {
    if (this.formatError) return { moneyFormat: { message: this.message() } };
    const value = this.currentValue();
    const min = this.bound('min');
    const max = this.bound('max');
    if (value !== null && Number.isFinite(min) && value < min) return { min: { min, actual: value } };
    if (value !== null && Number.isFinite(max) && value > max) return { max: { max, actual: value } };
    return null;
  }

  @HostListener('focus') onFocus(): void {
    this.focused = true;
    if (this.readonly) return;
    // O valor aparece completo e selecionado: a primeira digitação substitui o número.
    this.legacyText = null;
    this.blankWhenCleared = this.digits === '';
    this.render();
    this.element.nativeElement.select();
  }

  @HostListener('keydown', ['$event']) onKeydown(event: KeyboardEvent): void {
    if (this.readonly) return;
    if (event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === 'Backspace' || event.key === 'Delete') {
      event.preventDefault();
      // Apagar um valor informado nunca deixa o campo em branco: termina em `R$ 0,00`.
      this.digits = this.digits.length > 1
        ? this.digits.slice(0, -1)
        : (this.blankWhenCleared ? '' : '0');
      this.commit();
      return;
    }
    if (/^[0-9]$/.test(event.key)) {
      event.preventDefault();
      const input = this.element.nativeElement;
      const replacesAll = input.selectionStart === 0 && input.selectionEnd === input.value.length;
      this.digits = this.normalize((replacesAll ? '' : this.digits) + event.key);
      this.commit();
      return;
    }
    // Letras, sinais, `%` e separadores não entram no campo; o cursor volta para o fim.
    if (event.key.length === 1) {
      event.preventDefault();
      this.setCaretToEnd();
    }
  }

  @HostListener('paste', ['$event']) onPaste(event: ClipboardEvent): void {
    if (this.readonly) return;
    event.preventDefault();
    const pasted = event.clipboardData?.getData('text') ?? '';
    this.digits = this.normalize(pasted.replace(/\D+/g, ''));
    this.commit();
  }

  /** Rede de segurança para teclados móveis que não emitem keydown reconhecível. */
  @HostListener('input') onInput(): void {
    if (this.readonly) return;
    const text = String(this.element.nativeElement.value).replace(/\D+/g, '');
    this.digits = this.normalize(text);
    this.commit();
  }

  @HostListener('blur') onBlur(): void {
    this.focused = false;
    if (this.readonly) return;
    this.render();
    if (!this.formatError) this.emit();
    this.onTouched();
    this.setValidity();
    this.validatorChanged();
    this.moneyValidity.emit(this.formatError);
  }

  private applyIncoming(numeric: number | null): void {
    if (numeric === null || !Number.isFinite(numeric)) {
      this.digits = '';
      this.negative = false;
      this.legacyText = null;
      this.formatError = false;
    } else {
      this.digits = String(Math.round(Math.abs(numeric) * 100));
      this.negative = numeric < 0;
      this.legacyText = this.hasLegacyPrecision(numeric) ? this.formatLegacy(numeric) : null;
      this.formatError = this.legacyText !== null;
    }
    if (!this.focused) this.render();
    this.setValidity();
    this.validatorChanged();
    this.moneyValidity.emit(this.formatError);
  }

  private commit(): void {
    this.formatError = false;
    this.negative = false;
    this.legacyText = null;
    this.render();
    this.emit();
    this.setValidity();
    this.validatorChanged();
    this.moneyValidity.emit(this.formatError);
  }

  private emit(): void {
    const value = this.currentValue();
    this.onChange(value);
    this.moneyInput.emit(value);
  }

  private render(): void {
    const input = this.element.nativeElement;
    input.value = this.legacyText ?? (this.digits === '' ? '' : this.format(this.signedValue() ?? 0));
    this.setCaretToEnd();
  }

  private currentValue(): number | null {
    return this.digits === '' ? null : this.signedValue();
  }

  private signedValue(): number | null {
    return (Number(this.digits) / 100) * (this.negative ? -1 : 1);
  }

  /** Zeros à esquerda não contam: `05` é `R$ 0,05` e `0` é `R$ 0,00`. */
  private normalize(digits: string): string {
    const trimmed = digits.replace(/^0+(?=\d)/, '');
    return trimmed.length > MAX_DIGITS ? trimmed.slice(-MAX_DIGITS) : trimmed;
  }

  private bound(attribute: 'min' | 'max'): number {
    const raw = this.element.nativeElement.getAttribute(attribute);
    return raw === null ? Number.NaN : Number(raw);
  }

  private setCaretToEnd(): void {
    const input = this.element.nativeElement;
    try { input.setSelectionRange(input.value.length, input.value.length); } catch { /* campos sem seleção */ }
  }

  private get readonly(): boolean {
    return this.element.nativeElement.readOnly;
  }

  private hasLegacyPrecision(value: number): boolean {
    return Math.abs(value * 100 - Math.round(value * 100)) > 1e-8;
  }

  /**
   * A API serializa Decimal como texto ("12.50"), então valores monetários chegam como
   * número ou string. Aceite os dois em vez de deixar o campo em branco.
   */
  private toNumber(value: number | string | null | undefined): number | null {
    if (value === null || value === undefined || value === '') return null;
    if (typeof value === 'number') return Number.isFinite(value) ? value : null;
    const text = String(value).trim();
    if (!text) return null;
    const numeric = text.includes(',')
      ? Number(text.replace(/\./g, '').replace(',', '.'))
      : Number(text.replace(/\s/g, ''));
    return Number.isFinite(numeric) ? numeric : null;
  }

  private format(value: number): string {
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(value);
  }

  private formatLegacy(value: number): string {
    const decimals = Math.min(8, Math.max(3, (String(value).split('.')[1] || '').length));
    return new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: decimals, maximumFractionDigits: decimals }).format(value);
  }

  private message(): string { return 'Use reais com vírgula e no máximo duas casas decimais.'; }

  private setValidity(): void {
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
