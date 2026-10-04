import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule],
  template: ` <main class="login-page">
    <section class="login-story">
      <div class="brand"><span class="brand-mark" aria-hidden="true"><svg viewBox="0 0 48 48" focusable="false"><path d="M12 36V12h13c7 0 11 3 11 9s-4 9-11 9H18" /><path d="M25 30l9-9" /></svg></span><strong>Parts ERP</strong></div>
      <div>
        <p class="kicker">Controle sem improviso</p>
        <h1>Peças certas.<br /><em>Estoque em dia.</em></h1>
        <p>Vendas, inventário e Mercado Livre em uma operação única, segura e rastreável.</p>
      </div>
      <small>Gestão desenhada para o balcão e para o online.</small>
    </section>
    <section class="login-panel">
      <form [formGroup]="form" (ngSubmit)="submit()">
        <p class="eyebrow">Acesso seguro</p>
        <h2>Bem-vindo de volta</h2>
        <p class="hint">Entre com o usuário criado na configuração inicial.</p>
        <label
          >E-mail<input
            type="email"
            formControlName="email"
            autocomplete="username"
            placeholder="voce@empresa.com" /></label
        ><label
          >Senha<input
            type="password"
            formControlName="password"
            autocomplete="current-password"
            placeholder="••••••••••••"
        /></label>
        @if (error()) {
          <div class="error">{{ error() }}</div>
        }
        <button class="primary full" type="submit" [disabled]="form.invalid || loading()">
          {{ loading() ? 'Entrando…' : 'Entrar no ERP' }}
        </button>
        <p class="security-note">🔒 Seus dados de acesso não são enviados a terceiros.</p>
      </form>
    </section>
  </main>`,
  styleUrl: './login.scss',
})
export class LoginPage {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });
  submit(): void {
    if (this.form.invalid) return;
    this.loading.set(true);
    this.error.set('');
    const { email, password } = this.form.getRawValue();
    this.auth
      .login(email, password)
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: () => this.router.navigateByUrl('/dashboard'),
        error: (err: HttpErrorResponse) =>
          this.error.set(err.error?.detail ?? 'Não foi possível entrar.'),
      });
  }
}
