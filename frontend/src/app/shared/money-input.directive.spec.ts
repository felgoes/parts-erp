import { Component, Type } from '@angular/core';
import { FormControl, FormGroup, ReactiveFormsModule } from '@angular/forms';
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

@Component({
  standalone: true,
  imports: [MoneyInputDirective],
  template: '<input appMoneyInput [appMoneyInput]="value" readonly />',
})
class MoneyReadonlyHost {
  value: number | null = 1234.56;
}

@Component({
  standalone: true,
  imports: [MoneyInputDirective, ReactiveFormsModule],
  template: '<form [formGroup]="form"><input appMoneyInput formControlName="amount" min="1" /></form>',
})
class MoneyFormHost {
  readonly form = new FormGroup({ amount: new FormControl<number | null>(0) });
}

/** Mesmo formato do campo: `Intl` usa espaço não separável depois do `R$`. */
function brl(value: number, decimals = 2): string {
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  }).format(value);
}

async function create<T>(component: Type<T>, configure?: (instance: T) => void) {
  TestBed.resetTestingModule();
  await TestBed.configureTestingModule({ imports: [component] }).compileComponents();
  const fixture = TestBed.createComponent(component);
  configure?.(fixture.componentInstance);
  fixture.detectChanges();
  const input = fixture.nativeElement.querySelector('input') as HTMLInputElement;
  return { fixture, input };
}

async function mount<T>(component: Type<T>, configure?: (instance: T) => void) {
  const context = await create(component, configure);
  focus(context.input);
  return context;
}

function focus(input: HTMLInputElement) {
  input.dispatchEvent(new Event('focus'));
}

function type(input: HTMLInputElement, key: string) {
  input.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
}

function paste(input: HTMLInputElement, text: string) {
  const event = new Event('paste', { bubbles: true, cancelable: true }) as Event & { clipboardData: { getData: () => string } };
  event.clipboardData = { getData: () => text };
  input.dispatchEvent(event);
}

describe('MoneyInputDirective', () => {
  it('mostra o formato completo e acrescenta cada dígito no fim', async () => {
    const { fixture, input } = await mount(MoneyInputHost);

    expect(input.value).toBe(brl(1234.56));

    type(input, '1');
    expect(input.value).toBe(brl(0.01));
    type(input, '2');
    expect(input.value).toBe(brl(0.12));
    type(input, '3');
    expect(input.value).toBe(brl(1.23));
    type(input, '4');
    expect(input.value).toBe(brl(12.34));
    expect(fixture.componentInstance.value).toBe(12.34);
  });

  it('apaga só o último dígito e mantém o campo formatado', async () => {
    const { input } = await mount(MoneyInputHost);

    for (const key of ['1', '2', '3', '4']) type(input, key);
    expect(input.value).toBe(brl(12.34));

    type(input, 'Backspace');
    expect(input.value).toBe(brl(1.23));
    type(input, 'Backspace');
    expect(input.value).toBe(brl(0.12));
    type(input, 'Backspace');
    expect(input.value).toBe(brl(0.01));
    type(input, 'Backspace');
    expect(input.value).toBe(brl(0));
  });

  it('ignora vírgula, ponto de milhar, R$ e letras', async () => {
    const { fixture, input } = await mount(MoneyInputHost);

    type(input, '1');
    expect(input.value).toBe(brl(0.01));

    for (const key of [',', '.', 'R', '$', '%', '-', 'a', ' ']) type(input, key);

    expect(input.value).toBe(brl(0.01));
    expect(fixture.componentInstance.value).toBe(0.01);
  });

  it('cola valores em reais e descarta caracteres inválidos', async () => {
    const { fixture, input } = await mount(MoneyInputHost);

    paste(input, 'R$ 1.234,56');
    expect(input.value).toBe(brl(1234.56));
    expect(fixture.componentInstance.value).toBe(1234.56);

    paste(input, 'abc 12,34 xyz');
    expect(input.value).toBe(brl(12.34));
    expect(fixture.componentInstance.value).toBe(12.34);
  });

  it('não deixa produzir três casas decimais pela digitação', async () => {
    const { fixture, input } = await mount(MoneyInputHost);

    input.value = '123,456';
    input.dispatchEvent(new Event('input', { bubbles: true }));

    expect(input.value).toBe(brl(1234.56));
    expect(fixture.componentInstance.value).toBe(1234.56);
    expect(input.hasAttribute('aria-invalid')).toBe(false);
  });

  it('mantém campo opcional em branco e trata zero como valor informado', async () => {
    const { fixture, input } = await mount(MoneyInputHost, (instance) => {
      instance.value = null;
    });

    expect(input.value).toBe('');

    type(input, '0');
    expect(input.value).toBe(brl(0));
    expect(fixture.componentInstance.value).toBe(0);

    type(input, 'Backspace');
    expect(input.value).toBe('');
    expect(fixture.componentInstance.value).toBeNull();
  });

  it('respeita o mínimo do campo e libera quando o valor alcança', async () => {
    const { fixture, input } = await mount(MoneyFormHost);

    expect(input.value).toBe(brl(0));
    expect(fixture.componentInstance.form.controls.amount.hasError('min')).toBe(true);

    type(input, '1');
    type(input, '2');
    expect(fixture.componentInstance.form.controls.amount.value).toBe(0.12);
    expect(fixture.componentInstance.form.controls.amount.hasError('min')).toBe(true);

    type(input, '3');
    expect(fixture.componentInstance.form.controls.amount.value).toBe(1.23);
    expect(fixture.componentInstance.form.controls.amount.valid).toBe(true);
  });

  it('continua sinalizando valor legado com mais de duas casas', async () => {
    const { input } = await create(MoneyInputHost, (instance) => {
      instance.value = 123.456;
    });

    expect(input.value).toBe(brl(123.456, 3));
    expect(input.getAttribute('aria-invalid')).toBe('true');
    const hint = input.nextElementSibling as HTMLElement;
    expect(hint.textContent).toContain('no máximo duas casas decimais');
  });

  it('não captura teclado em campo somente leitura', async () => {
    const { input } = await mount(MoneyReadonlyHost);

    expect(input.value).toBe(brl(1234.56));
    type(input, '9');
    expect(input.value).toBe(brl(1234.56));
  });

  it('exibe valores que a API envia como texto decimal', async () => {
    for (const raw of ['1234.56', '1.234,56']) {
      const { input } = await create(MoneyInputHost, (instance) => {
        (instance as { value: unknown }).value = raw;
      });
      expect(input.value).toBe(brl(1234.56));
    }
  });
});
