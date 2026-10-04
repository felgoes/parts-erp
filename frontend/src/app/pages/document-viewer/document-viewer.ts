import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { ApiService } from '../../core/api.service';

@Component({
  selector: 'app-document-viewer',
  template: `
    <main class="document-viewer">
      <header><a href="/dashboard" aria-label="Voltar ao Parts ERP"><span> P </span><strong>Parts ERP</strong></a><small>Visualização de documento</small></header>
      @if (loading()) { <section class="viewer-state">Abrindo documento…</section> }
      @if (error()) { <section class="viewer-state error">Não foi possível abrir este documento.</section> }
      @if (pdfUrl(); as url) { <iframe [src]="url" title="Documento fiscal em PDF"></iframe> }
      @if (xml(); as content) { <pre>{{ content }}</pre> }
    </main>
  `,
  styles: [`
    :host { display:block; min-height:100vh; background:#f4f3ee; color:#223129; }
    .document-viewer { min-height:100vh; display:flex; flex-direction:column; }
    header { display:flex; align-items:center; justify-content:space-between; gap:18px; padding:16px 24px; background:#17271f; color:#fff; }
    header a { display:flex; align-items:center; gap:10px; color:#fff; text-decoration:none; }
    header a span { display:grid; place-items:center; width:32px; height:32px; border-radius:10px 10px 10px 3px; background:#b9dc52; color:#17271f; font-weight:900; transform:rotate(-3deg); }
    header small { color:#b9c9c0; }
    iframe { flex:1; width:100%; min-height:calc(100vh - 65px); border:0; background:#fff; }
    pre { flex:1; margin:20px; padding:20px; overflow:auto; white-space:pre-wrap; background:#fff; border:1px solid #dedfd8; font:12px/1.55 ui-monospace,monospace; }
    .viewer-state { margin:auto; padding:30px; color:#748078; }
    .viewer-state.error { color:#a33b2c; }
    @media (max-width:600px) { header { padding:14px 16px; } header small { font-size:11px; } pre { margin:12px; padding:14px; } }
  `],
})
export class DocumentViewerPage implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(ApiService);
  private readonly sanitizer = inject(DomSanitizer);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly pdfUrl = signal<SafeResourceUrl | null>(null);
  readonly xml = signal<string | null>(null);
  private objectUrl: string | null = null;

  ngOnInit() {
    const invoiceId = this.route.snapshot.paramMap.get('invoiceId');
    const documentId = this.route.snapshot.paramMap.get('documentId');
    if (!invoiceId || !documentId) { this.loading.set(false); this.error.set(true); return; }
    this.api.downloadInvoiceDocument(invoiceId, documentId).subscribe({
      next: (blob) => {
        this.objectUrl = URL.createObjectURL(blob);
        if (blob.type.includes('pdf')) this.pdfUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.objectUrl));
        else blob.text().then((value) => this.xml.set(value));
        this.loading.set(false);
      },
      error: () => { this.loading.set(false); this.error.set(true); },
    });
  }
  ngOnDestroy() { if (this.objectUrl) URL.revokeObjectURL(this.objectUrl); }
}
