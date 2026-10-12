export type PushSound = 'system' | 'bell' | 'chime' | 'soft' | 'kaching' | 'silent';
export interface PushPreference {
  category: string;
  label: string;
  description: string;
  enabled: boolean;
  sound: PushSound;
}

export interface PushNotification {
  id: string;
  category: string;
  title: string;
  body: string;
  status: string;
  created_at: string;
  sent_at: string | null;
  data: Record<string, string>;
}
