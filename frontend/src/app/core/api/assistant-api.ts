import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { apiUrl } from '../api-url';
import {
  AssistantActionResult,
  AssistantConfiguration,
  AssistantConversation,
  AssistantConversationSummary,
  AssistantPendingAction,
  AssistantTurn,
} from '../models/assistant';

@Injectable({ providedIn: 'root' })
export class AssistantApi {
  private readonly http = inject(HttpClient);

  configuration(): Observable<AssistantConfiguration> {
    return this.http.get<AssistantConfiguration>(apiUrl('/assistant/configuration'));
  }

  saveConfiguration(payload: Record<string, unknown>): Observable<AssistantConfiguration> {
    return this.http.put<AssistantConfiguration>(apiUrl('/assistant/configuration'), payload);
  }

  testConnection(payload: {
    provider: string;
    model: string;
    api_key?: string;
  }): Observable<{ ok: boolean; provider: string; model: string; reply: string }> {
    return this.http.post<{ ok: boolean; provider: string; model: string; reply: string }>(
      apiUrl('/assistant/configuration/test'),
      payload,
    );
  }

  conversations(): Observable<AssistantConversationSummary[]> {
    return this.http.get<AssistantConversationSummary[]>(
      apiUrl('/assistant/conversations'),
    );
  }

  createConversation(): Observable<AssistantConversationSummary> {
    return this.http.post<AssistantConversationSummary>(
      apiUrl('/assistant/conversations'),
      {},
    );
  }

  conversation(id: string): Observable<AssistantConversation> {
    return this.http.get<AssistantConversation>(
      apiUrl(`/assistant/conversations/${id}`),
    );
  }

  deleteConversation(id: string): Observable<void> {
    return this.http.delete<void>(apiUrl(`/assistant/conversations/${id}`));
  }

  sendMessage(id: string, message: string): Observable<AssistantTurn> {
    return this.http.post<AssistantTurn>(
      apiUrl(`/assistant/conversations/${id}/messages`),
      { message },
    );
  }

  actions(id: string): Observable<AssistantPendingAction[]> {
    return this.http.get<AssistantPendingAction[]>(
      apiUrl(`/assistant/conversations/${id}/actions`),
    );
  }

  confirmAction(id: string): Observable<AssistantActionResult> {
    return this.http.post<AssistantActionResult>(
      apiUrl(`/assistant/actions/${id}/confirm`),
      {},
    );
  }

  cancelAction(id: string): Observable<{ status: string; message: string }> {
    return this.http.post<{ status: string; message: string }>(
      apiUrl(`/assistant/actions/${id}/cancel`),
      {},
    );
  }
}
