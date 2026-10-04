import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { finalize } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { User } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-users',
  imports: [ReactiveFormsModule, PageHeader],
  template: `
    <app-page-header eyebrow="Acesso" title="Usuários" subtitle="Gerencie quem pode acessar o Parts ERP."
      ><button class="primary" (click)="openNew()">+ Novo usuário</button></app-page-header
    >
    <section class="card table-card">
      <div class="table-wrap">
        <table>
          <thead><tr><th>Nome</th><th>E-mail</th><th>Perfil</th><th></th></tr></thead>
          <tbody>
            @for (user of users(); track user.id) {
              <tr>
                <td><strong>{{ user.full_name }}</strong></td>
                <td>{{ user.email }}</td>
                <td><span class="badge">{{ roleLabel(user.role) }}</span></td>
                <td><button class="secondary small" type="button" (click)="openEdit(user)">Editar acesso</button></td>
              </tr>
            } @empty {
              <tr><td colspan="4"><div class="empty">Nenhum usuário encontrado.</div></td></tr>
            }
          </tbody>
        </table>
      </div>
    </section>
    @if (modal()) {
      <div class="modal-backdrop" (click)="close()">
        <section class="modal" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <div><p class="eyebrow">Acesso</p><h2>Novo usuário</h2></div>
            <button class="close" type="button" (click)="close()">×</button>
          </div>
          <form [formGroup]="userForm" (ngSubmit)="save()">
            <div class="form-grid">
              <label>Nome completo<input formControlName="full_name" autocomplete="name" /></label>
              <label>E-mail<input type="email" formControlName="email" autocomplete="email" /></label>
              <label>Senha<input type="password" formControlName="password" autocomplete="new-password" /><small>Mínimo de 12 caracteres.</small></label>
              <label>Perfil<select formControlName="role"><option value="operator">Operador</option><option value="manager">Gerente</option><option value="admin">Administrador</option></select></label>
            </div>
            @if (message()) { <p class="form-message error">{{ message() }}</p> }
            <button class="primary full" [disabled]="userForm.invalid || saving()">
              {{ saving() ? 'Cadastrando…' : 'Cadastrar usuário' }}
            </button>
          </form>
        </section>
      </div>
    }
    @if (resetModal()) {
      <div class="modal-backdrop" (click)="closeReset()">
        <section class="modal" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <div><p class="eyebrow">Acesso</p><h2>Editar usuário</h2></div>
            <button class="close" type="button" (click)="closeReset()">×</button>
          </div>
          <p>Altere o e-mail e, se necessário, defina uma nova senha para <strong>{{ selectedUser()?.full_name }}</strong>.</p>
          <form [formGroup]="resetForm" (ngSubmit)="resetPassword()">
            <label>E-mail<input type="email" formControlName="email" autocomplete="email" /></label>
            <label>Nova senha<input type="password" formControlName="password" autocomplete="new-password" placeholder="Deixe vazio para manter" /><small>Se preencher, use mínimo de 12 caracteres.</small></label>
            @if (resetMessage()) { <p class="form-message error">{{ resetMessage() }}</p> }
            <button class="primary full" [disabled]="resetForm.invalid || resetting()">{{ resetting() ? 'Salvando…' : 'Salvar nova senha' }}</button>
          </form>
        </section>
      </div>
    }
  `,
  styleUrl: './users.scss',
})
export class UsersPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly fb = inject(FormBuilder);
  readonly users = signal<User[]>([]);
  readonly modal = signal(false);
  readonly saving = signal(false);
  readonly message = signal('');
  readonly resetModal = signal(false);
  readonly selectedUser = signal<User | null>(null);
  readonly resetting = signal(false);
  readonly resetMessage = signal('');
  readonly userForm = this.fb.nonNullable.group({
    full_name: ['', [Validators.required, Validators.minLength(2)]],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(12)]],
    role: ['operator' as User['role'], Validators.required],
  });
  readonly resetForm = this.fb.nonNullable.group({
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.minLength(12)]],
  });

  ngOnInit() {
    this.load();
  }

  load() {
    this.api.users().subscribe({ next: (users) => this.users.set(users) });
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
    this.resetForm.reset({ email: user.email, password: '' });
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
    const payload = values.password ? values : { email: values.email };
    this.api.updateUser(user.id, payload)
      .pipe(finalize(() => this.resetting.set(false)))
      .subscribe({ next: () => this.closeReset(), error: () => this.resetMessage.set('Não foi possível redefinir a senha.') });
  }

  roleLabel(role: User['role']) {
    return { admin: 'Administrador', manager: 'Gerente', operator: 'Operador' }[role];
  }

  save() {
    if (this.userForm.invalid) return;
    this.saving.set(true);
    this.message.set('');
    this.api.createUser(this.userForm.getRawValue()).pipe(finalize(() => this.saving.set(false))).subscribe({
      next: () => {
        this.close();
        this.load();
      },
      error: (error) => {
        this.message.set(error.status === 409 ? 'Já existe um usuário com este e-mail.' : 'Não foi possível cadastrar o usuário.');
      },
    });
  }
}
