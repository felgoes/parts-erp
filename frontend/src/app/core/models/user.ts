export interface User {
  id: string;
  email: string;
  full_name: string;
  role: 'admin' | 'manager' | 'operator' | 'stock' | 'finance' | 'viewer';
  active: boolean;
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
}
export interface AuthToken {
  access_token: string;
  token_type: string;
  persistent?: boolean;
  user: User;
}
