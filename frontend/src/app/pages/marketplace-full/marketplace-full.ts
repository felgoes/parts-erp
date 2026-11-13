import { DatePipe, JsonPipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { apiUrl } from '../../core/api-url';
import { AuthService } from '../../core/auth.service';
import { DateRange, quickDateRange } from '../../core/quick-date-ranges';
import { PageHeader } from '../../shared/page-header';
import { PeriodFilter } from '../../shared/period-filter';

type FullInventory = {
  inventory_id: string;
  total: number | null;
  available_quantity: number | null;
  not_available_quantity: number | null;
  not_available_detail: any[];
  links: any[];
  local_stock: { sku: string; name: string; quantity: number } | null;
  synced_at: string | null;
  sync_status: string;
};
type FullShipment = {
  id: string;
  inbound_id: string | null;
  display_id: string;
  status: string;
  delivery_mode: string | null;
  distribution_center: string | null;
  panel_url: string | null;
  scheduled_at: string | null;
  updated_at: string;
  items: any[];
  timeline: any[];
  api_reception: boolean;
  manual_stage_recorded: boolean;
  needs_review: boolean;
};

@Component({
  selector: 'app-marketplace-full',
  imports: [DatePipe, JsonPipe, FormsModule, RouterLink, PageHeader, PeriodFilter],
  templateUrl: './marketplace-full.html',
  styleUrl: './marketplace-full.scss',
})
export class MarketplaceFullPage implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly base = apiUrl('/integrations/mercadolivre/full');

  readonly tab = signal<'shipments' | 'inventory' | 'operations'>('shipments');
  readonly connected = signal<boolean | null>(null);
  readonly nickname = signal('');
  readonly lastSync = signal<string | null>(null);
  readonly loading = signal(false);
  readonly syncing = signal(false);
  readonly error = signal('');
  readonly feedback = signal('');
  readonly canEdit = computed(() => ['admin', 'manager'].includes(this.auth.user()?.role || ''));
  readonly inventory = signal<FullInventory[]>([]);
  readonly stockSummary = signal({ available: 0, unavailable: 0, stored: 0, partial: false, missing: 0 });
  readonly shipments = signal<FullShipment[]>([]);
  readonly operations = signal<any[]>([]);
  readonly operationTypeFilter = signal('');
  readonly operationInboundFilter = signal('');
  readonly operationOffset = signal(0);
  readonly operationNextOffset = signal<number | null>(null);
  readonly selected = signal<FullShipment | null>(null);
  readonly showForm = signal(false);
  readonly replenishment = signal<any | null>(null);
  readonly replenishmentChecked = signal(false);
  readonly q = signal('');
  readonly statusFilter = signal('');
  readonly centerFilter = signal('');
  readonly initialRange = quickDateRange('last30');
  readonly startDate = signal(this.initialRange.startDate);
  readonly endDate = signal(this.initialRange.endDate);

  form = {
    display_id: '', inbound_id: '', delivery_mode: 'vehicle', distribution_center: '',
    scheduled_at: '', expected_processing_at: '', physically_received_at: '', panel_url: '',
    notes: '',
  };
  readonly shipmentItems = signal<any[]>([this.emptyShipmentItem()]);
  eventForm = { stage: 'received', operational_at: '', note: '' };

  ngOnInit(): void {
    this.loadStatus();
    this.load();
  }

  loadStatus(): void {
    this.http.get<any>(this.base + '/status').subscribe({
      next: (value) => {
        this.connected.set(value.connected);
        this.nickname.set(value.nickname || '');
        this.lastSync.set(value.last_sync);
      },
      error: () => this.connected.set(false),
    });
  }

  load(): void {
    this.loading.set(true);
    this.error.set('');
    if (this.tab() === 'shipments') {
      this.http.get<FullShipment[]>(this.base + '/shipments', {
        params: { ...(this.q() ? { q: this.q() } : {}), ...(this.statusFilter() ? { status: this.statusFilter() } : {}), ...(this.centerFilter() ? { distribution_center: this.centerFilter() } : {}), date_from: this.startDate(), date_to: this.endDate() },
      }).subscribe({
        next: (value) => {
          this.shipments.set(value);
          this.loading.set(false);
          const id = this.selected()?.id;
          if (id) this.selected.set(value.find((shipment) => shipment.id === id) || null);
        },
        error: () => this.fail(),
      });
    } else if (this.tab() === 'inventory') {
      this.http.get<any>(this.base + '/inventory', {
        params: {
          ...(this.q() ? { q: this.q() } : {}),
          ...(this.statusFilter() === 'low' ? { low: 'true' } : {}),
          ...(this.statusFilter() === 'zero' ? { zero: 'true' } : {}),
          ...(this.statusFilter() === 'unavailable' ? { unavailable: 'true' } : {}),
        },
      }).subscribe({
        next: (value) => { this.inventory.set(value.items || []); this.stockSummary.set(value.summary || { available: 0, unavailable: 0, stored: 0, partial: false, missing: 0 }); this.loading.set(false); },
        error: () => this.fail(),
      });
    } else {
      this.http.get<any>(this.base + '/operations', {
        params: { ...(this.q() ? { sku: this.q() } : {}), ...(this.operationTypeFilter() ? { operation_type: this.operationTypeFilter() } : {}), ...(this.operationInboundFilter() ? { inbound_id: this.operationInboundFilter() } : {}), date_from: this.startDate(), date_to: this.endDate(), offset: String(this.operationOffset()), limit: '100' },
      }).subscribe({
        next: (value) => { this.operations.set(this.operationOffset() ? [...this.operations(), ...(value.items || [])] : (value.items || [])); this.operationNextOffset.set(value.next_offset ?? null); this.loading.set(false); },
        error: () => this.fail(),
      });
    }
  }

  private fail(): void {
    this.loading.set(false);
    this.error.set('Não foi possível carregar os dados do Full. Confira a integração e tente novamente.');
  }

  setTab(value: 'shipments' | 'inventory' | 'operations'): void {
    this.tab.set(value);
    this.selected.set(null);
    this.statusFilter.set('');
    this.load();
  }

  keyTab(event: KeyboardEvent): void {
    if (!['ArrowRight', 'ArrowLeft'].includes(event.key)) return;
    event.preventDefault();
    const tabs = ['shipments', 'inventory', 'operations'] as const;
    const index = tabs.indexOf(this.tab());
    this.setTab(tabs[(index + (event.key === 'ArrowRight' ? 1 : 2)) % 3]);
    (event.target as HTMLElement).parentElement
      ?.querySelectorAll<HTMLButtonElement>('button')[tabs.indexOf(this.tab())]?.focus();
  }

  loadMoreOperations(): void { if (this.operationNextOffset() === null) return; this.operationOffset.set(this.operationNextOffset()!); this.load(); }

  applyPeriod(range: DateRange): void {
    this.startDate.set(range.startDate);
    this.endDate.set(range.endDate);
    this.operationOffset.set(0);
    this.load();
  }

  sync(): void {
    if (this.syncing() || !this.connected()) return;
    this.syncing.set(true);
    this.http.post<any>(this.base + '/sync', {}).subscribe({
      next: () => {
        this.feedback.set('Sincronização solicitada.');
        this.syncing.set(false);
        setTimeout(() => { this.loadStatus(); this.load(); }, 1800);
      },
      error: () => { this.syncing.set(false); this.feedback.set('Não foi possível iniciar a sincronização.'); },
    });
  }

  replenishmentProductId = '';
  checkReplenishment(userProductId: string): void {
    if (!userProductId) return;
    this.replenishmentProductId = userProductId;
    this.http.get<any>(this.base + '/replenishment/' + encodeURIComponent(userProductId)).subscribe({
      next: (value) => { this.replenishment.set(value); this.replenishmentChecked.set(true); },
      error: () => {
        this.replenishment.set({ available: false, reason: 'Não foi possível consultar o recurso agora.' });
        this.replenishmentChecked.set(true);
      },
    });
  }

  emptyShipmentItem(): any { return { sku: '', inventory_id: '', item_id: '', variation_id: '', product_name: '', declared_quantity: 0, physical_count: null, discrepancy_note: '' }; }
  addShipmentItem(): void { this.shipmentItems.update((items) => [...items, this.emptyShipmentItem()]); }
  removeShipmentItem(index: number): void { this.shipmentItems.update((items) => items.filter((_, i) => i !== index)); }

  requestBackfill(): void {
    const start = this.startDate(); const end = this.endDate();
    if (!start || !end || start > end || (new Date(end).getTime() - new Date(start).getTime()) / 86400000 > 59) { this.feedback.set('O backfill aceita janelas de até 60 dias. Ajuste o período.'); return; }
    this.http.post<any>(this.base + '/operations/backfill', null, { params: { date_from: start, date_to: end } }).subscribe({ next: (value) => this.feedback.set(value.message), error: () => this.feedback.set('Não foi possível solicitar o backfill desta janela.') });
  }

  saveShipment(): void {
    if (!this.form.display_id.trim()) {
      this.feedback.set('Informe o identificador do envio.');
      return;
    }
    const form = this.form;
    const payload = {
      display_id: form.display_id,
      inbound_id: form.inbound_id || null,
      delivery_mode: form.delivery_mode || null,
      distribution_center: form.distribution_center || null,
      scheduled_at: form.scheduled_at || null,
      expected_processing_at: form.expected_processing_at || null,
      physically_received_at: form.physically_received_at || null,
      panel_url: form.panel_url || null,
      notes: form.notes || null,
      items: this.shipmentItems().filter((item) => item.sku || item.inventory_id || item.item_id).map((item) => ({ ...item, declared_quantity: Number(item.declared_quantity) || 0, physical_count: item.physical_count === '' ? null : item.physical_count })),
    };
    this.http.post<FullShipment>(this.base + '/shipments', payload).subscribe({
      next: (shipment) => {
        this.showForm.set(false);
        this.form = { ...form, display_id: '', inbound_id: '' };
        this.shipmentItems.set([this.emptyShipmentItem()]);
        this.feedback.set('Envio registrado com trilha de auditoria.');
        this.load();
        this.selected.set(shipment);
      },
      error: () => this.feedback.set('Não foi possível salvar o envio. Confira o identificador e os dados.'),
    });
  }

  addEvent(): void {
    const shipment = this.selected();
    if (!shipment || !this.eventForm.operational_at) return;
    this.http.post(this.base + '/shipments/' + shipment.id + '/events', {
      stage: this.eventForm.stage,
      operational_at: new Date(this.eventForm.operational_at + '-03:00').toISOString(),
      note: this.eventForm.note || null,
    }).subscribe({
      next: () => { this.feedback.set('Etapa manual auditada.'); this.load(); },
      error: () => this.feedback.set('Não foi possível registrar a etapa.'),
    });
  }

  openShipment(shipment: FullShipment): void { this.selected.set(shipment); }
  label(stage: string): string {
    return ({
      pending: 'Recebimento pendente', received: 'Recebido no CD',
      processing: 'Processamento em andamento', completed: 'Processamento finalizado',
      cancelled: 'Cancelado', api_reception: 'Recepção registrada pelo Mercado Livre',
    } as Record<string, string>)[stage] || stage;
  }
  movementType(type: string): string {
    return ({ INBOUND_RECEPTION: 'Recepção Full', SALE: 'Venda Full', RETURN: 'Devolução', WITHDRAWAL: 'Retirada', ADJUSTMENT: 'Ajuste' } as Record<string, string>)[type] || type;
  }
  movementDeltas(detail: any): string {
    return Object.entries(detail || {}).map(([key, raw]) => {
      let value: any = raw;
      if (value && typeof value === 'object') value = value.delta ?? value.quantity ?? value.value ?? JSON.stringify(value);
      const number = Number(value);
      return Number.isFinite(number) ? key + ': ' + (number > 0 ? '+' : '') + number : key + ': ' + String(value);
    }).join(' · ') || 'Delta não informado';
  }
  reason(detail: any): string { return detail?.type || detail?.reason || detail?.code || detail?.condition || 'Outro motivo'; }
  availableTotal(): number { return this.stockSummary().available; }
  unavailableTotal(): number { return this.stockSummary().unavailable; }
  storedTotal(): number { return this.stockSummary().stored; }
  panelLink(url: string | null): string { return url || 'https://www.mercadolivre.com.br/gestao-envios-full'; }
}
