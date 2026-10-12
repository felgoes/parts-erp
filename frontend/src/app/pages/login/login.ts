import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';
import { finalize } from 'rxjs';
import { AuthService } from '../../core/auth.service';

@Component({
  selector: 'app-login',
  imports: [ReactiveFormsModule],
  templateUrl: './login.html',
  styleUrl: './login.scss',
})
export class LoginPage implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  readonly loading = signal(false);
  readonly error = signal('');
  readonly biometricAvailable = signal(false);
  readonly biometricConfigured = signal(false);
  readonly biometricEmail = signal<string | null>(null);
  readonly enableBiometric = signal(false);
  readonly staySignedIn = signal(true);
  readonly form = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', Validators.required],
  });
  async ngOnInit(): Promise<void> {
    const status = await this.auth.biometricStatus();
    this.biometricAvailable.set(status.available);
    this.biometricConfigured.set(status.configured);
    this.biometricEmail.set(status.email);
    if (status.available && status.configured) {
      await this.loginWithBiometric();
    }
  }
  toggleBiometric(event: Event): void {
    this.enableBiometric.set((event.target as HTMLInputElement).checked);
  }
  toggleStaySignedIn(event: Event): void {
    this.staySignedIn.set((event.target as HTMLInputElement).checked);
  }
  submit(): void {
    if (this.form.invalid) return;
    this.loading.set(true);
    this.error.set('');
    const { email, password } = this.form.getRawValue();
    this.auth
      .login(email, password, this.staySignedIn())
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: async () => {
          if (this.enableBiometric()) {
            try {
              await this.auth.enableBiometric(email);
            } catch {
              // The password login remains valid if enrollment is cancelled.
            }
          }
          await this.router.navigateByUrl('/dashboard');
        },
        error: (err: HttpErrorResponse) =>
          this.error.set(err.error?.detail ?? 'Não foi possível entrar.'),
      });
  }
  async loginWithBiometric(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      await this.auth.loginWithBiometric();
      await this.router.navigateByUrl('/dashboard');
    } catch (error) {
      const response = error as HttpErrorResponse & { code?: string };
      if (response.code !== 'BIOMETRIC_CANCELLED') {
        this.error.set(
          response.error?.detail ?? 'Não foi possível entrar com a digital. Use e-mail e senha.',
        );
        const status = await this.auth.biometricStatus();
        this.biometricConfigured.set(status.configured);
      }
    } finally {
      this.loading.set(false);
    }
  }
}
