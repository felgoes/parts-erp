import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { AssistantApi } from '../../core/api/assistant-api';
import { AssistantConfiguration } from '../../core/models/assistant';

@Component({
  selector: 'app-settings-ai',
  imports: [FormsModule],
  templateUrl: './settings-ai.html',
  styleUrl: './company-settings.scss',
})
export class SettingsAi implements OnInit {
  private readonly api = inject(AssistantApi);
  readonly configuration = signal<AssistantConfiguration | null>(null);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly testing = signal(false);
  readonly message = signal('');
  readonly error = signal('');
  form = {
    provider: '',
    model: '',
    api_key: '',
    monthly_budget_usd: null as number | null,
  };

  ngOnInit(): void {
    this.load();
  }

  models() {
    return (
      this.configuration()?.providers.find((provider) => provider.id === this.form.provider)
        ?.models ?? []
    );
  }

  selectedProvider() {
    return this.configuration()?.providers.find(
      (provider) => provider.id === this.form.provider,
    );
  }

  changeProvider(): void {
    this.form.model = this.models()[0]?.id ?? '';
  }

  save(removeKey = false): void {
    const current = this.configuration();
    const sameProvider = current?.provider === this.form.provider;
    const keyAction = removeKey
      ? 'remove'
      : this.form.api_key.trim()
        ? 'replace'
        : sameProvider
          ? 'keep'
          : 'remove';
    this.saving.set(true);
    this.message.set('');
    this.error.set('');
    this.api
      .saveConfiguration({
        provider: this.form.provider,
        model: this.form.model,
        key_action: keyAction,
        api_key: keyAction === 'replace' ? this.form.api_key.trim() : undefined,
        monthly_budget_usd: this.form.monthly_budget_usd,
      })
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (config) => {
          this.applyConfiguration(config);
          this.message.set(
            removeKey
              ? 'Chave removida. Estudos continuam no modo determinístico.'
              : 'Configuração única de IA salva. Estudos e assistente usarão este conector.',
          );
        },
        error: (err: { error?: { detail?: string } }) =>
          this.error.set(err.error?.detail || 'Não foi possível salvar a configuração de IA.'),
      });
  }

  test(): void {
    this.testing.set(true);
    this.message.set('');
    this.error.set('');
    this.api
      .testConnection({
        provider: this.form.provider,
        model: this.form.model,
        api_key: this.form.api_key.trim() || undefined,
      })
      .pipe(finalize(() => this.testing.set(false)))
      .subscribe({
        next: () => this.message.set('O provedor respondeu corretamente ao teste.'),
        error: (err: { error?: { detail?: string } }) =>
          this.error.set(err.error?.detail || 'O provedor não respondeu ao teste.'),
      });
  }

  private load(): void {
    this.api
      .configuration()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (config) => this.applyConfiguration(config),
        error: () => this.error.set('Não foi possível carregar a configuração de IA.'),
      });
  }

  private applyConfiguration(config: AssistantConfiguration): void {
    this.configuration.set(config);
    const provider = config.provider || config.providers[0]?.id || '';
    const models = config.providers.find((item) => item.id === provider)?.models ?? [];
    this.form = {
      provider,
      model: config.model || models[0]?.id || '',
      api_key: '',
      monthly_budget_usd: config.budget.monthly_limit_usd
        ? Number(config.budget.monthly_limit_usd)
        : null,
    };
  }
}
