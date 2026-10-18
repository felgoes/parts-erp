export interface AssistantModel {
  id: string;
  label: string;
  input_per_million_usd: string;
  output_per_million_usd: string;
}

export interface AssistantProvider {
  id: string;
  label: string;
  models: AssistantModel[];
  pricing_updated_at: string;
  pricing_source: string;
}

export interface AssistantBudget {
  monthly_limit_usd: string | null;
  used_usd: string;
  percent_used: string | null;
  alert: boolean;
  blocked: boolean;
  resets_at: string;
  currency: string;
  pricing_updated_at: string | null;
}

export interface AssistantConfiguration {
  provider: string | null;
  model: string | null;
  has_api_key: boolean;
  budget: AssistantBudget;
  providers: AssistantProvider[];
}

export interface AssistantConversationSummary {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
}

export interface AssistantMessage {
  id: string;
  role: string;
  content: string;
  created_at: string;
}

export interface AssistantConversation extends AssistantConversationSummary {
  messages: AssistantMessage[];
}

export interface AssistantPendingAction {
  id: string;
  conversation_id: string;
  summary: string;
  status: string;
  tool: string;
  created_at: string;
  expires_at: string;
  expired: boolean;
}

export interface AssistantTurn {
  message: string;
  pending_actions: AssistantPendingAction[];
  provider: string;
  model: string;
  budget: AssistantBudget;
}

export interface AssistantActionResult {
  action: AssistantPendingAction;
  result: Record<string, unknown>;
  message: string;
}
