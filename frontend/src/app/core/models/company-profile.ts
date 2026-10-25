export type TaxRegime =
  | 'simples_nacional'
  | 'mei'
  | 'lucro_presumido'
  | 'lucro_real'
  | 'nao_informado';

export interface CompanyProfileData {
  identification: {
    legal_name: string | null;
    trade_name: string | null;
    cnpj: string | null;
    branch: 'matriz' | 'filial' | 'nao_informado';
    registration_status: string | null;
    inactive_status_acknowledged: boolean;
    status_date: string | null;
    status_reason: string | null;
    opened_on: string | null;
    legal_nature_code: string | null;
    legal_nature_description: string | null;
    company_size: string | null;
    simples_opt_in: boolean | null;
    mei_opt_in: boolean | null;
    state_registration: string | null;
    municipal_registration: string | null;
  };
  activities: {
    primary_cnae_code: string | null;
    primary_cnae_description: string | null;
    secondary_cnaes: string[];
    erp_activity: string | null;
    retail_relevant: boolean | null;
    wholesale_relevant: boolean | null;
  };
  addresses: {
    fiscal: CompanyAddress;
    commercial_same_as_fiscal: boolean;
    commercial: CompanyAddress | null;
  };
  contact: { phone: string | null; business_email: string | null };
  fiscal: {
    tax_regime: TaxRegime;
    icms_taxpayer: boolean | null;
    icms_rule: string | null;
    icms_rate_pct: string | null;
    effective_on: string | null;
    notes: string | null;
  };
  market_study: {
    target_margin_pct: string | null;
    channel_commission_pct: string | null;
    fixed_sale_fee: string | null;
    outbound_shipping_rule: string | null;
    expected_return_pct: string | null;
    default_region: string | null;
    default_category: string | null;
    presentation_currency: 'BRL';
  };
  import_profile: {
    enabled: boolean | null;
    radar_modality: string | null;
    default_incoterm: 'FOB' | 'EXW' | 'CIF' | 'nao_informado';
    preferred_mode: 'maritimo' | 'aereo' | 'nao_informado';
    destination_port: string | null;
    clearance_state: string | null;
    exchange_spread_pct: string | null;
    logistics_operator: string | null;
    insurance_rule: string | null;
    terminal_handling_rule: string | null;
    storage_rule: string | null;
    domestic_freight_rule: string | null;
    notes: string | null;
  };
  cnpj_card_import?: {
    sha256: string;
    content_type: string;
    reading: string;
    imported_at: string;
    retained: false;
  } | null;
  field_sources: Record<string, 'manual' | 'cnpj_card' | 'official' | 'default'>;
}

export interface CompanyAddress {
  postal_code: string | null;
  street: string | null;
  number: string | null;
  complement: string | null;
  district: string | null;
  city: string | null;
  state: string | null;
  country: string;
}

export interface CompanyCompleteness {
  purpose: string;
  label: string;
  percent: number;
  missing: string[];
}

export interface CompanyProfile {
  id: string;
  revision: number;
  data: CompanyProfileData;
  manual_fields: string[];
  completeness: CompanyCompleteness[];
  updated_at: string | null;
}

export interface CnpjCardField {
  value: unknown;
  confidence: 'high' | 'medium' | 'low';
  origin: 'cnpj_card';
}

export interface CnpjCardParse {
  document: {
    sha256: string;
    content_type: string;
    reading: string;
    ocr_quality: number | null;
    retained: false;
  };
  fields: Record<string, CnpjCardField>;
  missing: string[];
  low_confidence: string[];
  differences: { field: string; current: unknown; extracted: unknown }[];
  protected_manual_fields: string[];
  cnpj_valid: boolean;
  status_warning: string | null;
  lookup_available: boolean;
  lookup_message: string;
}
