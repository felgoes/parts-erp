import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { MoneyInputDirective } from './money-input.directive';

@Component({
  standalone: true,
  imports: [MoneyInputDirective],
  template: '<input appMoneyInput [appMoneyInput]="value" (moneyInput)="value = $event" />',
})
class MoneyInputHost {
  value: number | null = 1234.56;
}

describe('MoneyInputDirective', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [MoneyInputHost] }).compileComponents();
  });

  it('uses plain editable text while focused and formats only after blur', () => {
    const fixture = TestBed.createComponent(MoneyInputHost);
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;

    input.setSelectionRange(input.value.length, input.value.length);
    input.dispatchEvent(new Event('focus'));
    expect(input.value).toBe('1234,56');

    input.value = '1234,5';
    input.setSelectionRange(input.value.length, input.value.length);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(input.value).toBe('1234,5');
    expect(input.selectionStart).toBe(6);
    expect(fixture.componentInstance.value).toBe(1234.5);

    input.dispatchEvent(new Event('blur'));
    expect(input.value).toContain('1.234,50');
    expect(fixture.componentInstance.value).toBe(1234.5);
  });

  it('selects a zero default when focused so a new amount replaces it directly', () => {
    const fixture = TestBed.createComponent(MoneyInputHost);
    fixture.componentInstance.value = 0;
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;

    input.dispatchEvent(new Event('focus'));
    expect(input.value).toBe('0,00');
    expect(input.selectionStart).toBe(0);
    expect(input.selectionEnd).toBe(input.value.length);
  });

  it('accepts a pasted Brazilian currency value without changing it during editing', () => {
    const fixture = TestBed.createComponent(MoneyInputHost);
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;

    input.dispatchEvent(new Event('focus'));
    input.value = 'R$ 1.234,56';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(input.value).toBe('R$ 1.234,56');
    expect(fixture.componentInstance.value).toBe(1234.56);

    input.dispatchEvent(new Event('blur'));
    expect(input.value).toContain('1.234,56');
  });

  it('keeps precision beyond cents invalid for correction', () => {
    const fixture = TestBed.createComponent(MoneyInputHost);
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;

    input.dispatchEvent(new Event('focus'));
    input.value = '123,456';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(input.value).toBe('123,456');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(fixture.componentInstance.value).toBeNull();
  });

  it('keeps the caret over the same digit when a formatted value becomes editable', () => {
    const fixture = TestBed.createComponent(MoneyInputHost);
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;

    expect(input.value).toContain('1.234,56');
    input.setSelectionRange(5, 5);
    input.dispatchEvent(new Event('focus'));
    expect(input.value).toBe('1234,56');
    expect(input.selectionStart).toBe(1);
    expect(input.selectionEnd).toBe(1);
  });

  it('keeps the caret where the user left it while typing and deleting', () => {
    const fixture = TestBed.createComponent(MoneyInputHost);
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;

    input.dispatchEvent(new Event('focus'));
    input.value = '1234,5';
    input.setSelectionRange(6, 6);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(input.value).toBe('1234,5');
    expect(input.selectionStart).toBe(6);
    expect(fixture.componentInstance.value).toBe(1234.5);

    input.value = '1234,';
    input.setSelectionRange(5, 5);
    input.dispatchEvent(new Event('input', { bubbles: true }));
    expect(input.value).toBe('1234,');
    expect(input.selectionStart).toBe(5);
    expect(fixture.componentInstance.value).toBe(1234);

    input.dispatchEvent(new Event('blur'));
    expect(input.value).toContain('1.234,00');
  });

  it('keeps excess decimals visible for correction after blur', () => {
    const fixture = TestBed.createComponent(MoneyInputHost);
    fixture.detectChanges();
    const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;

    input.dispatchEvent(new Event('focus'));
    input.value = '123,456';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('blur'));

    expect(input.value).toBe('123,456');
    expect(input.getAttribute('aria-invalid')).toBe('true');
    expect(fixture.componentInstance.value).toBeNull();
    const hint = input.nextElementSibling as HTMLElement;
    expect(hint.textContent).toContain('no máximo duas casas decimais');
    expect(hint.hasAttribute('hidden')).toBe(false);
  });
});
