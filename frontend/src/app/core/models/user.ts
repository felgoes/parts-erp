export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'manager' | 'operator' | 'stock' | 'finance' | 'viewer';
  active: boolean;
  financial_summary_hidden: boolean;
}
export interface ErpSettings {
  company_name: string;
  company_short_name: string;
  logo_data_url: string | null;
  backup_enabled: boolean;
  backup_frequency: 'daily' | 'weekly';
  backup_time: string;
  backup_retention_days: number;
  backup_destination: 'google_drive';
  backup_ready: boolean;
  backup_status: 'setup_required' | 'ready';
  drive_client_id: string | null;
  drive_client_secret_configured: boolean;
  drive_folder_id: string | null;
  drive_connected: boolean;
  backup_last_at: string | null;
  backup_last_status: string;
  backup_last_error: string | null;
  backup_last_success_at: string | null;
  backup_last_attempt_at: string | null;
  backup_next_run_at: string | null;
  backup_state: string;
  backup_last_error_code: string | null;
  backup_local_dir: string | null;
}
export interface AuthToken {
  access_token: string;
  token_type: string;
  persistent?: boolean;
  user: User;
}

/** Origem (IP) barrada temporariamente por excesso de tentativas de login. */
export interface BlockedLoginOrigin {
  ip: string;
  failures: number;
  seconds_left: number;
}

/** Conta com falhas acumuladas: sofre atraso progressivo, mas nunca fica bloqueada. */
export interface DelayedLoginAccount {
  email: string;
  failures: number;
  delay_seconds: number;
  seconds_left: number;
}

/** Estado do limite de tentativas de login, para a tela de Usuários. */
export interface LoginAttempts {
  window_seconds: number;
  ip_failure_limit: number;
  delay_cap_seconds: number;
  blocked_origins: BlockedLoginOrigin[];
  delayed_accounts: DelayedLoginAccount[];
}
