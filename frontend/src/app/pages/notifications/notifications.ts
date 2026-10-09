import { DatePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { ApiService } from '../../core/api.service';
import { PushNotification, PushPreference, PushSound } from '../../core/models';
import { PushNotificationsService } from '../../core/push-notifications.service';
import { PageHeader } from '../../shared/page-header';

@Component({
  selector: 'app-notifications',
  imports: [DatePipe, PageHeader],
  template: `
    <app-page-header eyebrow="Central de alertas" title="Notificações" subtitle="Escolha o que merece sua atenção e consulte o histórico do ERP." />
    <article class="panel device-status" [class.ok]="pushState().status === 'registered'" [class.failed]="pushState().status === 'error'">
      <span class="device-status-icon" aria-hidden="true">{{ pushState().status === 'registered' ? '✓' : pushState().status === 'error' ? '!' : '•' }}</span>
      <div><p class="eyebrow">Este dispositivo</p><h2>{{ pushStatusTitle() }}</h2><small>{{ pushState().message }}</small></div>
      @if (pushState().status === 'error') { <button type="button" class="refresh" (click)="retryPush()">Tentar novamente</button> }
    </article>
    <section class="notification-grid">
      <article class="panel preferences">
        <div class="section-head"><div><p class="eyebrow">Preferências</p><h2>O que você quer receber?</h2></div><span class="muted">Por usuário</span></div>
        @for (preference of preferences(); track preference.category) {
          <div class="preference" [class.saving]="saving() === preference.category">
            <span class="preference-copy"><strong>{{ preference.label }}</strong><small>{{ preference.description }}</small></span>
            <div class="preference-controls">
              <label class="receive-control"><input type="checkbox" [checked]="preference.enabled" [disabled]="saving() === preference.category" (change)="toggle(preference, $event)" /> Receber</label>
              <label class="sound-control" [for]="'sound-' + preference.category">Som
                <select [id]="'sound-' + preference.category" [disabled]="saving() === preference.category" (change)="setSound(preference, $event)">
                  @for (sound of sounds; track sound.value) { <option [value]="sound.value" [selected]="sound.value === preference.sound">{{ sound.label }}</option> }
                </select>
              </label>
              <button class="preview" type="button" [disabled]="!canPreview(preference.sound)" (click)="preview(preference.sound)" [attr.aria-label]="'Ouvir prévia: ' + preference.label">▶</button>
            </div>
          </div>
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
    .device-status { display:flex; align-items:center; gap:14px; margin-bottom:18px; } .device-status > div { flex:1; } .device-status h2 { margin:3px 0 4px; } .device-status small { color:var(--muted,#738078); } .device-status-icon { display:grid; place-items:center; width:38px; height:38px; flex:none; border-radius:50%; background:#edf0ed; color:#657068; font-size:20px; font-weight:900; } .device-status.ok { border-color:#a9d6b5; background:#f4fbf6; } .device-status.ok .device-status-icon { background:#d9f0df; color:#21723a; } .device-status.failed { border-color:#e2b5ae; background:#fff7f5; } .device-status.failed .device-status-icon { background:#f5d9d4; color:#a83e30; }
    .section-head { display:flex; justify-content:space-between; align-items:flex-start; gap:12px; margin-bottom:16px; } h2 { margin:3px 0 0; font-size:21px; } .eyebrow { margin:0; color:var(--accent,#6d8f29); font-size:11px; font-weight:800; letter-spacing:.12em; text-transform:uppercase; } .muted,.empty { color:var(--muted,#738078); font-size:13px; }
    .preference { display:flex; flex-direction:column; align-items:stretch; gap:12px; padding:16px 0; border-top:1px solid var(--line,#e5e8e4); } .preference-copy { display:grid; gap:4px; min-width:0; } .preference small { color:var(--muted,#738078); line-height:1.4; } .preference-controls { display:flex; align-items:center; justify-content:space-between; gap:8px; width:100%; } .receive-control,.sound-control { display:flex; align-items:center; gap:7px; font-size:12px; color:var(--muted,#738078); white-space:nowrap; } .preference input { width:19px; height:19px; accent-color:#1c4433; } .sound-control { flex:1; justify-content:space-between; } .sound-control select { min-height:38px; max-width:140px; padding:6px 8px; border:1px solid var(--line,#ccd6cf); border-radius:8px; color:var(--text,#26352c); background:var(--surface,#fff); font:inherit; } .preview { width:36px; height:36px; flex:none; border:1px solid var(--line,#ccd6cf); border-radius:50%; background:transparent; color:var(--text,#26352c); cursor:pointer; } .preview:disabled { opacity:.4; cursor:default; }
    .refresh { border:1px solid var(--line,#ccd6cf); border-radius:9px; background:transparent; padding:8px 12px; font-weight:700; color:inherit; } .history-item { display:flex; gap:12px; padding:15px 0; border-top:1px solid var(--line,#e5e8e4); } .dot { width:9px; height:9px; margin-top:6px; flex:none; border-radius:50%; background:#42aa67; } .dot.failed { background:#c44b3a; } .history-item strong { display:block; } .history-item p { margin:4px 0; color:var(--muted,#738078); } .history-item small { color:var(--muted,#738078); font-size:11px; }
    @media (max-width:760px) { .notification-grid { grid-template-columns:1fr; } .panel { padding:18px; } .device-status { align-items:flex-start; flex-wrap:wrap; } .device-status .refresh { margin-left:52px; } .preference { align-items:stretch; flex-direction:column; } .preference-controls { width:100%; flex-wrap:wrap; } .sound-control { flex:1; justify-content:space-between; } .sound-control select { flex:1; max-width:220px; } }
  `],
})
export class NotificationsPage implements OnInit {
  private readonly api = inject(ApiService);
  private readonly pushNotifications = inject(PushNotificationsService);
  readonly pushState = this.pushNotifications.registrationState;
  readonly preferences = signal<PushPreference[]>([]);
  readonly history = signal<PushNotification[]>([]);
  readonly loading = signal(true);
  readonly saving = signal<string | null>(null);
  readonly sounds: { value: PushSound; label: string }[] = [
    { value: 'system', label: 'Padrão do Android' },
    { value: 'bell', label: 'Sino' },
    { value: 'chime', label: 'Toque' },
    { value: 'soft', label: 'Suave' },
    { value: 'kaching', label: 'Kaching' },
    { value: 'silent', label: 'Silencioso' },
  ];
  private previewAudio: HTMLAudioElement | null = null;
  ngOnInit() { void this.pushNotifications.enableForCurrentDevice(); this.load(); }
  load() { this.loading.set(true); this.api.pushPreferences().subscribe({ next: (value) => this.preferences.set(value), error: () => {}, complete: () => this.loading.set(false) }); this.api.pushHistory().subscribe({ next: (value) => this.history.set(value) }); }
  retryPush() { void this.pushNotifications.enableForCurrentDevice(); }
  pushStatusTitle() { return this.pushState().status === 'registered' ? 'Push ativado' : this.pushState().status === 'error' ? 'Push não registrado' : this.pushState().status === 'checking' ? 'Verificando push' : 'Verificação disponível no Android'; }
  toggle(preference: PushPreference, event: Event) { const enabled = (event.target as HTMLInputElement).checked; this.update(preference, enabled, preference.sound); }
  setSound(preference: PushPreference, event: Event) { const sound = (event.target as HTMLSelectElement).value as PushSound; this.update(preference, preference.enabled, sound); }
  canPreview(sound: PushSound) { return sound === 'bell' || sound === 'chime' || sound === 'soft' || sound === 'kaching'; }
  preview(sound: PushSound) {
    if (!this.canPreview(sound)) return;
    this.previewAudio?.pause();
    const extension = sound === 'kaching' ? 'mp3' : 'wav';
    this.previewAudio = new Audio('/sounds/notification-' + sound + '.' + extension);
    void this.previewAudio.play();
  }
  private update(preference: PushPreference, enabled: boolean, sound: PushSound) {
    this.saving.set(preference.category);
    this.api.updatePushPreference(preference.category, enabled, sound).subscribe({
      next: (value) => this.preferences.update(items => items.map(item => item.category === value.category ? value : item)),
      error: () => this.saving.set(null),
      complete: () => this.saving.set(null),
    });
  }
  status(value: string) { return value === 'sent' ? 'Enviado' : value === 'failed' ? 'Falhou' : 'Pendente'; }
}
