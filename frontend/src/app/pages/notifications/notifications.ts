import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { PushNotification, PushPreference } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-notifications',
  imports: [DatePipe, PageHeader],
  template: `
    <app-page-header eyebrow="Central de alertas" title="Notificações" subtitle="Escolha o que merece sua atenção e consulte o histórico do ERP." />
    <section class="notification-grid">
      <article class="panel preferences">
        <div class="section-head"><div><p class="eyebrow">Preferências</p><h2>O que você quer receber?</h2></div><span class="muted">Por usuário</span></div>
        @for (preference of preferences(); track preference.category) {
          <label class="preference" [class.saving]="saving() === preference.category">
            <span class="preference-copy"><strong>{{ preference.label }}</strong><small>{{ preference.description }}</small></span>
            <input type="checkbox" [checked]="preference.enabled" [disabled]="saving() === preference.category" (change)="toggle(preference, $event)" />
          </label>
        }
      </article>
      <article class="panel history">
        <div class="section-head"><div><p class="eyebrow">Atividade recente</p><h2>Histórico de pushs</h2></div><button type="button" class="refresh" (click)="load()">Atualizar</button></div>
        @if (loading()) { <p class="empty">Carregando notificações…</p> }
        @for (item of history(); track item.id) {
          <div class="history-item"><span class="dot" [class.failed]="item.status === 'failed'"></span><div><strong>{{ item.title }}</strong><p>{{ item.body }}</p><small>{{ item.created_at | date:'dd/MM/yyyy HH:mm' }} · {{ status(item.status) }}</small></div></div>
        } @empty { @if (!loading()) { <p class="empty">Nenhuma notificação registrada ainda.</p> } }
      </article>
    </section>
  `,
  styles: [`
    :host { display:block; padding-bottom:40px; }
    .notification-grid { display:grid; grid-template-columns:minmax(280px,.8fr) minmax(360px,1.2fr); gap:18px; }
    .panel { background:var(--surface,#fff); border:1px solid var(--line,#dfe4de); border-radius:16px; padding:22px; }
    .section-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:16px; } h2 { margin:3px 0 0; font-size:21px; } .eyebrow { margin:0; color:var(--accent,#6d8f29); font-size:11px; font-weight:800; letter-spacing:.12em; text-transform:uppercase; } .muted,.empty { color:var(--muted,#738078); font-size:13px; }
    .preference { display:flex; align-items:center; justify-content:space-between; gap:16px; padding:16px 0; border-top:1px solid var(--line,#e5e8e4); cursor:pointer; } .preference-copy { display:grid; gap:4px; } .preference small { color:var(--muted,#738078); line-height:1.4; } input { width:21px; height:21px; accent-color:#1c4433; }
    .refresh { border:1px solid var(--line,#ccd6cf); border-radius:9px; background:transparent; padding:8px 12px; font-weight:700; color:inherit; } .history-item { display:flex; gap:12px; padding:15px 0; border-top:1px solid var(--line,#e5e8e4); } .dot { width:9px; height:9px; margin-top:6px; flex:none; border-radius:50%; background:#42aa67; } .dot.failed { background:#c44b3a; } .history-item strong { display:block; } .history-item p { margin:4px 0; color:var(--muted,#738078); } .history-item small { color:var(--muted,#738078); font-size:11px; }
    @media (max-width:760px) { .notification-grid { grid-template-columns:1fr; } .panel { padding:18px; } }
  `],
})
export class NotificationsPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly preferences = signal<PushPreference[]>([]);
  readonly history = signal<PushNotification[]>([]);
  readonly loading = signal(true);
  readonly saving = signal<string | null>(null);
  ngOnInit() { this.load(); }
  load() { this.loading.set(true); this.api.pushPreferences().subscribe({ next: (value) => this.preferences.set(value), error: () => {}, complete: () => this.loading.set(false) }); this.api.pushHistory().subscribe({ next: (value) => this.history.set(value) }); }
  toggle(preference: PushPreference, event: Event) { const enabled = (event.target as HTMLInputElement).checked; this.saving.set(preference.category); this.api.updatePushPreference(preference.category, enabled).subscribe({ next: (value) => this.preferences.update(items => items.map(item => item.category === value.category ? value : item)), error: () => {}, complete: () => this.saving.set(null) }); }
  status(value: string) { return value === 'sent' ? 'Enviado' : value === 'failed' ? 'Falhou' : 'Pendente'; }
}
