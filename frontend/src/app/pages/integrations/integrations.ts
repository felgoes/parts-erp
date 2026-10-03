import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ApiService } from '../../core/api.service';
import { MarketplaceConfig, MarketplaceStatus } from '../../core/models';
import { PageHeader } from '../../shared/page-header';

type MarketplaceForm = {
  client_id: string;
  client_secret: string;
  redirect_uri: string;
  site_id: string;
  import_orders: boolean;
  automatic_stock: boolean;
  sync_documents: boolean;
};

@Component({
  selector: 'app-integrations',
  imports: [FormsModule, PageHeader],
  template: `
    <app-page-header eyebrow="Configuração" title="Integrações" subtitle="Mercado Livre"></app-page-header>
    <section class="settings-layout">
      <form class="settings-panel" (ngSubmit)="save()">
        <div class="section-title"><div><h2>Aplicação Mercado Livre</h2><p>Informe os dados cadastrados no painel de desenvolvedores.</p></div><span class="status" [class.ok]="status()?.configured">{{ status()?.configured ? 'Configurado' : 'Pendente' }}</span></div>
        <div class="form-grid">
          <label>Client ID<input name="client_id" [(ngModel)]="form.client_id" required /></label>
          <label>Client secret<input name="client_secret" type="password" [(ngModel)]="form.client_secret" [placeholder]="config()?.client_secret_configured ? 'Mantido — informe apenas para trocar' : 'Informe o segredo'" /></label>
          <label class="span-2">URL de callback<input name="redirect_uri" [(ngModel)]="form.redirect_uri" required /></label>
          <label>Site<select name="site_id" [(ngModel)]="form.site_id"><option value="MLB">MLB — Brasil</option></select></label>
        </div>
        <div class="section-title rules"><div><h2>Regras de sincronização</h2><p>Defina o que o ERP deve processar automaticamente.</p></div></div>
        <label class="check"><input type="checkbox" name="import_orders" [(ngModel)]="form.import_orders" /><span><strong>Importar pedidos</strong><small>Receber pedidos pagos por webhook.</small></span></label>
        <label class="check"><input type="checkbox" name="automatic_stock" [(ngModel)]="form.automatic_stock" /><span><strong>Baixar estoque automaticamente</strong><small>Conferir SKU e registrar a saída uma única vez.</small></span></label>
        <label class="check"><input type="checkbox" name="sync_documents" [(ngModel)]="form.sync_documents" /><span><strong>Sincronizar XML e DANFE</strong><small>Buscar documentos fiscais após a autorização.</small></span></label>
        <div class="form-actions"><button class="primary" [disabled]="saving()">{{ saving() ? 'Salvando…' : 'Salvar configuração' }}</button><button type="button" class="text-button" (click)="connect()" [disabled]="!status()?.configured || connecting()">{{ connecting() ? 'Abrindo…' : 'Conectar conta' }}</button></div>
        @if (message()) { <p class="form-message">{{ message() }}</p> }
      </form>
      <aside class="help-panel"><div class="ml-mark">M</div><h2>Mercado Livre</h2><p>Os endpoints oficiais são fixos no servidor. A tela controla as credenciais e as regras da operação sem expor o segredo depois de salvo.</p><dl><dt>Conta</dt><dd>{{ status()?.connected ? 'Conectada' : 'Ainda não conectada' }}</dd><dt>Callback</dt><dd>Deve ser igual ao cadastrado no Mercado Livre.</dd></dl></aside>
    </section>
  `,
  styleUrl: './integrations.scss',
})
export class IntegrationsPage implements OnInit {
  private readonly api = inject(ApiService);
  readonly status = signal<MarketplaceStatus | null>(null);
  readonly config = signal<MarketplaceConfig | null>(null);
  readonly saving = signal(false);
  readonly connecting = signal(false);
  readonly message = signal('');
  form: MarketplaceForm = { client_id: '', client_secret: '', redirect_uri: '', site_id: 'MLB', import_orders: true, automatic_stock: true, sync_documents: true };
  ngOnInit() { this.api.marketplaceStatus().subscribe((v) => this.status.set(v)); this.api.marketplaceConfig().subscribe((v) => { this.config.set(v); this.form = { ...this.form, ...v, client_secret: '' }; }); }
  save() { this.saving.set(true); this.message.set(''); const payload = { ...this.form, client_secret: this.form.client_secret || undefined }; this.api.saveMarketplaceConfig(payload).subscribe({ next: (v) => { this.config.set(v); this.form = { ...this.form, ...v, client_secret: '' }; this.status.update((s) => s ? { ...s, configured: true } : s); this.message.set('Configuração salva.'); this.saving.set(false); }, error: () => { this.message.set('Não foi possível salvar.'); this.saving.set(false); } }); }
  connect() { this.connecting.set(true); this.api.connectMarketplace().subscribe({ next: (v) => location.assign(v.authorization_url), error: () => this.connecting.set(false) }); }
}
