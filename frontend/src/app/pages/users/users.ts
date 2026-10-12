import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { UsersApi } from '../../core/api/users-api';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LoginAttempts, User } from '../../core/models';
import { ROLE_DESCRIPTIONS, ROLE_LABELS, canManageUsers } from '../../core/user-access';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-users',
  imports: [ReactiveFormsModule, PageHeader],
  templateUrl: './users.html',
  styleUrl: './users.scss',
})
export class UsersPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly access = inject(UsersApi);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);
  readonly users = signal<User[]>([]);
  readonly attempts = signal<LoginAttempts | null>(null);
  readonly releaseEmail = signal('');
  readonly releasing = signal(false);
  readonly attemptsMessage = signal('');
  readonly modal = signal(false);
  readonly saving = signal(false);
  readonly message = signal('');
  readonly resetModal = signal(false);
  readonly selectedUser = signal<User | null>(null);
  readonly resetting = signal(false);
  readonly resetMessage = signal('');
  readonly roleChoices: User['role'][] = [
    'operator',
    'stock',
    'finance',
    'manager',
    'viewer',
    'admin',
  ];
  readonly userForm = this.fb.nonNullable.group({
    full_name: ['', [Validators.required, Validators.minLength(2)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(12)]],
    role: ['operator' as User['role'], Validators.required],
  });
  readonly resetForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    role: ['operator' as User['role'], Validators.required],
    active: [true],
    password: ['', [Validators.minLength(12)]],
  });

  ngOnInit() {
    this.load();
    this.loadAttempts();
  }

  load() {
    this.api.users().subscribe({ next: (users) => this.users.set(users) });
  }

  canManageUsers() {
    return canManageUsers(this.auth.user()?.role);
  }

  loadAttempts() {
    if (!this.canManageUsers()) return;
    this.attemptsMessage.set('');
    this.access.loginAttempts().subscribe({
      next: (state) => this.attempts.set(state),
      error: () => this.attemptsMessage.set('Não foi possível consultar as tentativas de login.'),
    });
  }

  release(payload: { email?: string; ip?: string }) {
    if (this.releasing()) return;
    this.releasing.set(true);
    this.access
      .releaseLoginAttempts(payload)
      .pipe(finalize(() => this.releasing.set(false)))
      .subscribe({
        next: (state) => {
          this.attempts.set(state);
          this.releaseEmail.set('');
        },
        error: (error) =>
          this.attemptsMessage.set(error.error?.detail || 'Não foi possível liberar o acesso.'),
      });
  }

  releaseByEmail() {
    const email = this.releaseEmail().trim();
    if (email) this.release({ email });
  }

  /** Tempo até a origem ser liberada, em linguagem de quem atende o telefone. */
  timeLeft(seconds: number) {
    if (seconds <= 0) return 'liberado';
    if (seconds < 60) return `${seconds} s`;
    return `${Math.ceil(seconds / 60)} min`;
  }

  openNew() {
    this.userForm.reset({ full_name: '', email: '', password: '', role: 'operator' });
    this.message.set('');
    this.modal.set(true);
  }

  close() {
    this.modal.set(false);
  }

  openEdit(user: User) {
    this.selectedUser.set(user);
    this.resetForm.reset({ email: user.email, role: user.role, active: user.active, password: '' });
    this.resetMessage.set('');
    this.resetModal.set(true);
  }

  closeReset() {
    this.resetModal.set(false);
    this.selectedUser.set(null);
  }

  resetPassword() {
    const user = this.selectedUser();
    if (!user || this.resetForm.invalid) return;
    this.resetting.set(true);
    this.resetMessage.set('');
    const values = this.resetForm.getRawValue();
    const payload = {
      email: values.email,
      role: values.role,
      active: values.active,
      ...(values.password ? { password: values.password } : {}),
    };
    this.api
      .updateUser(user.id, payload)
      .pipe(finalize(() => this.resetting.set(false)))
      .subscribe({
        next: () => {
          this.closeReset();
          this.load();
        },
        error: (error) =>
          this.resetMessage.set(
            error.error?.detail || 'Não foi possível salvar as alterações do usuário.',
          ),
      });
  }

  roleLabel(role: User['role']) {
    return ROLE_LABELS[role];
  }

  roleDescription(role: User['role']) {
    return ROLE_DESCRIPTIONS[role];
  }

  save() {
    if (this.userForm.invalid) return;
    this.saving.set(true);
    this.message.set('');
    this.api
      .createUser(this.userForm.getRawValue())
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: () => {
          this.close();
          this.load();
        },
        error: (error) => {
          this.message.set(
            error.status === 409
              ? 'Já existe um usuário com este e-mail.'
              : 'Não foi possível cadastrar o usuário.',
          );
        },
      });
  }
}
