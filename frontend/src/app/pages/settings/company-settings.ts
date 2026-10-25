import { DatePipe, DecimalPipe, KeyValuePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { finalize } from 'rxjs';
import { CompanyApi } from '../../core/api/company-api';
import {
  CnpjCardParse,
  CompanyProfile,
  CompanyProfileData,
} from '../../core/models/company-profile';

export const EMPTY_COMPANY_PROFILE: CompanyProfileData = {
  identification: {
    legal_name: null,
    trade_name: null,
    cnpj: null,
    branch: 'nao_informado',
    registration_status: null,
    inactive_status_acknowledged: false,
    status_date: null,
    status_reason: null,
    opened_on: null,
    legal_nature_code: null,
    legal_nature_description: null,
    company_size: null,
    simples_opt_in: null,
    mei_opt_in: null,
    state_registration: null,
    municipal_registration: null,
  },
  activities: {
    primary_cnae_code: null,
    primary_cnae_description: null,
    secondary_cnaes: [],
    erp_activity: null,
    retail_relevant: null,
    wholesale_relevant: null,
  },
  addresses: {
    fiscal: {
      postal_code: null,
      street: null,
      number: null,
      complement: null,
      district: null,
      city: null,
      state: null,
      country: 'Brasil',
    },
    commercial_same_as_fiscal: true,
    commercial: null,
  },
  contact: { phone: null, business_email: null },
  fiscal: {
    tax_regime: 'nao_informado',
    icms_taxpayer: null,
    icms_rule: null,
    icms_rate_pct: null,
    effective_on: null,
    notes: null,
  },
  market_study: {
    target_margin_pct: '25',
    channel_commission_pct: null,
    fixed_sale_fee: null,
    outbound_shipping_rule: null,
    expected_return_pct: null,
    default_region: null,
    default_category: null,
    presentation_currency: 'BRL',
  },
  import_profile: {
    enabled: null,
    radar_modality: null,
    default_incoterm: 'nao_informado',
    preferred_mode: 'nao_informado',
    destination_port: null,
    clearance_state: null,
    exchange_spread_pct: '3',
    logistics_operator: null,
    insurance_rule: null,
    terminal_handling_rule: null,
    storage_rule: null,
    domestic_freight_rule: null,
    notes: null,
  },
  cnpj_card_import: null,
  field_sources: {
    'market_study.target_margin_pct': 'default',
    'import_profile.exchange_spread_pct': 'default',
  },
};

@Component({
  selector: 'app-company-settings',
  imports: [DatePipe, DecimalPipe, FormsModule, KeyValuePipe],
  templateUrl: './company-settings.html',
  styleUrl: './company-settings.scss',
})
export class CompanySettings implements OnInit {
  private readonly companyApi = inject(CompanyApi);
  readonly profile = signal<CompanyProfile | null>(null);
  readonly draft = signal<CompanyProfileData>(structuredClone(EMPTY_COMPANY_PROFILE));
  readonly tab = signal<'empresa' | 'fiscal' | 'estudo' | 'importacao'>('empresa');
  readonly selectedFields = signal<Record<string, boolean>>({});
  readonly cardPreview = signal<CnpjCardParse | null>(null);
  readonly history = signal<
    Array<{
      id: string;
      revision: number;
      changed_fields: string[];
      changed_by: string | null;
      created_at: string;
    }>
  >([]);
  readonly loading = signal(true);
  readonly saving = signal(false);
  readonly parsing = signal(false);
  readonly message = signal('');
  readonly error = signal('');

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.companyApi
      .profile()
      .pipe(finalize(() => this.loading.set(false)))
      .subscribe({
        next: (profile) => this.applyProfile(profile),
        error: (err) =>
          this.error.set(err?.error?.detail || 'Não foi possível carregar o cadastro da empresa.'),
      });
    this.companyApi.history().subscribe({
      next: (history) => this.history.set(history),
      error: () => undefined,
    });
  }

  markManual(path: string): void {
    const data = structuredClone(this.draft());
    data.field_sources[path] = 'manual';
    this.draft.set(data);
  }

  setSecondaryCnaes(value: string): void {
    this.draft().activities.secondary_cnaes = value
      .split(/[;,\n]/)
      .map((item) => item.trim())
      .filter(Boolean);
    this.markManual('activities.secondary_cnaes');
  }

  setCommercialSame(value: boolean): void {
    this.draft().addresses.commercial_same_as_fiscal = value;
    if (!value && !this.draft().addresses.commercial) {
      this.draft().addresses.commercial = structuredClone(this.draft().addresses.fiscal);
    }
    this.markManual('addresses.commercial_same_as_fiscal');
  }

  parseCard(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.parseCardFile(file);
  }

  dropCard(event: DragEvent): void {
    event.preventDefault();
    const file = event.dataTransfer?.files?.[0];
    if (file) this.parseCardFile(file);
  }

  private parseCardFile(file: File): void {
    this.error.set('');
    this.message.set('');
    this.parsing.set(true);
    this.companyApi
      .parseCard(file)
      .pipe(finalize(() => this.parsing.set(false)))
      .subscribe({
        next: (result) => {
          const selected: Record<string, boolean> = {};
          for (const path of Object.keys(result.fields)) {
            selected[path] = !result.protected_manual_fields.includes(path);
          }
          this.selectedFields.set(selected);
          this.cardPreview.set(result);
        },
        error: (err) =>
          this.error.set(err?.error?.detail || 'Não foi possível ler o Cartão CNPJ.'),
      });
  }

  applyParsed(): void {
    const preview = this.cardPreview();
    if (!preview) return;
    const data = structuredClone(this.draft());
    for (const [path, field] of Object.entries(preview.fields)) {
      if (!this.selectedFields()[path]) continue;
      this.setPath(data, path, field.value);
      data.field_sources[path] = 'cnpj_card';
    }
    data.cnpj_card_import = {
      ...preview.document,
      imported_at: new Date().toISOString(),
    };
    this.draft.set(data);
    this.message.set('Campos selecionados aplicados ao rascunho. Revise antes de salvar.');
    this.cardPreview.set(null);
    if (preview.status_warning) this.error.set(preview.status_warning);
  }

  toggleCardField(path: string, selected: boolean): void {
    this.selectedFields.set({ ...this.selectedFields(), [path]: selected });
  }

  save(): void {
    this.error.set('');
    this.message.set('');
    this.saving.set(true);
    this.companyApi
      .save(this.profile()?.revision ?? 0, this.draft(), this.manualPaths())
      .pipe(finalize(() => this.saving.set(false)))
      .subscribe({
        next: (profile) => {
          this.applyProfile(profile);
          this.message.set('Cadastro da empresa salvo com uma nova versão de auditoria.');
          this.companyApi.history().subscribe((history) => this.history.set(history));
        },
        error: (err) =>
          this.error.set(
            err?.error?.detail ||
              'Não foi possível salvar o cadastro. Recarregue e confira os dados.',
          ),
      });
  }

  completeness(purpose: string): number {
    return this.profile()?.completeness.find((row) => row.purpose === purpose)?.percent ?? 0;
  }

  protectedFields(): string[] {
    return this.cardPreview()?.protected_manual_fields ?? [];
  }

  fieldLabel(path: string): string {
    return (
      {
        'identification.cnpj': 'CNPJ',
        'identification.legal_name': 'Razão social',
        'identification.trade_name': 'Nome fantasia',
        'identification.branch': 'Matriz ou filial',
        'identification.registration_status': 'Situação cadastral',
        'identification.status_date': 'Data da situação',
        'identification.status_reason': 'Motivo da situação',
        'identification.opened_on': 'Data de abertura',
        'identification.legal_nature_code': 'Código da natureza jurídica',
        'identification.legal_nature_description': 'Natureza jurídica',
        'identification.company_size': 'Porte',
        'identification.simples_opt_in': 'Simples Nacional',
        'identification.mei_opt_in': 'MEI',
        'activities.primary_cnae_code': 'CNAE principal',
        'activities.primary_cnae_description': 'Descrição do CNAE',
        'activities.secondary_cnaes': 'CNAEs secundários',
        'addresses.fiscal.postal_code': 'CEP',
        'addresses.fiscal.street': 'Logradouro',
        'addresses.fiscal.number': 'Número',
        'addresses.fiscal.complement': 'Complemento',
        'addresses.fiscal.district': 'Bairro',
        'addresses.fiscal.city': 'Município',
        'addresses.fiscal.state': 'UF',
        'contact.phone': 'Telefone',
        'contact.business_email': 'E-mail',
      } as Record<string, string>
    )[path] ?? path;
  }

  private applyProfile(profile: CompanyProfile): void {
    this.profile.set(profile);
    this.draft.set(structuredClone(profile.data));
  }

  private manualPaths(): string[] {
    const fields = Object.entries(this.draft().field_sources)
      .filter(([, source]) => source === 'manual')
      .map(([path]) => path);
    const previous = this.profile()?.manual_fields ?? [];
    const before = this.flatten(this.profile()?.data ?? EMPTY_COMPANY_PROFILE);
    const after = this.flatten(this.draft());
    const changed = Object.keys(after).filter(
      (path) => JSON.stringify(before[path]) !== JSON.stringify(after[path]),
    );
    return [...new Set([...previous, ...fields, ...changed])];
  }

  private flatten(value: unknown, prefix = ''): Record<string, unknown> {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return { [prefix]: value };
    return Object.entries(value).reduce<Record<string, unknown>>((result, [key, child]) => {
      const path = prefix ? `${prefix}.${key}` : key;
      return { ...result, ...this.flatten(child, path) };
    }, {});
  }

  private setPath(target: CompanyProfileData, path: string, value: unknown): void {
    const parts = path.split('.');
    let cursor: Record<string, unknown> = target as unknown as Record<string, unknown>;
    for (const part of parts.slice(0, -1)) {
      const next = cursor[part];
      if (!next || typeof next !== 'object' || Array.isArray(next)) {
        cursor[part] = {};
      }
      cursor = cursor[part] as Record<string, unknown>;
    }
    cursor[parts.at(-1)!] = value;
  }
}
