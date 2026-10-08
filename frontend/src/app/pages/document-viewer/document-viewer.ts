import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { Capacitor, registerPlugin } from '@capacitor/core';
import { Browser } from '@capacitor/browser';
import { firstValueFrom } from 'rxjs';
import { ApiService } from '../../core/api.service';

type DocumentOpenerPlugin = { openUrl(options: { url: string }): Promise<void>; open(options: { base64: string; mimeType: string; fileName: string }): Promise<{ saved?: boolean; fileName?: string }> };
const documentOpener = registerPlugin<DocumentOpenerPlugin>('DocumentOpener');

@Component({
  selector: 'app-document-viewer',
  template: `
    <main class="document-viewer">
      <header><a href="/dashboard" aria-label="Voltar ao Parts ERP"><span> P </span><strong>Parts ERP</strong></a><small>Visualização de documento</small></header>
      @if (loading()) { <section class="viewer-state">Abrindo documento…</section> }
      @if (error()) { <section class="viewer-state error">Não foi possível abrir este documento.</section> }
      @if (nativeReady()) { <section class="viewer-state native-ready"><strong>Documento pronto</strong><span>O arquivo será aberto no navegador do celular.</span><button type="button" (click)="openNativeDocument()">Abrir no navegador</button>@if (nativeError()) { <small class="error-text">{{ nativeError() }}</small> }</section> }
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
    .native-ready { display:grid; gap:10px; text-align:center; }
    .native-ready strong { color:#223129; font-size:18px; }
    .native-ready button { border:0; border-radius:10px; padding:12px 18px; background:#193d2e; color:#fff; font-weight:700; }
    .native-ready .error-text { color:#a33b2c; }
    @media (max-width:600px) { header { padding:14px 16px; } header small { font-size:11px; } pre { margin:12px; padding:14px; } }
  `],
})
export class DocumentViewerPage implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly api = inject(ApiService);
  private readonly sanitizer = inject(DomSanitizer);
  readonly loading = signal(true);
  readonly error = signal(false);
  readonly nativeReady = signal(false);
  readonly nativeError = signal<string | null>(null);
  readonly pdfUrl = signal<SafeResourceUrl | null>(null);
  readonly xml = signal<string | null>(null);
  private objectUrl: string | null = null;
  private nativeBase64 = '';
  private nativeFileName = 'documento.pdf';

  ngOnInit() {
    const invoiceId = this.route.snapshot.paramMap.get('invoiceId');
    const documentId = this.route.snapshot.paramMap.get('documentId');
    if (!invoiceId || !documentId) { this.loading.set(false); this.error.set(true); return; }
    this.api.downloadInvoiceDocument(invoiceId, documentId).subscribe({
      next: async (blob) => {
        this.objectUrl = URL.createObjectURL(blob);
        if (blob.type.includes('pdf')) {
          if (Capacitor.isNativePlatform()) {
            this.nativeBase64 = await this.toBase64(blob);
            this.nativeFileName = `documento-${documentId}.pdf`;
            this.nativeReady.set(true);
            void this.openBrowserDocument(invoiceId, documentId);
          } else {
            this.pdfUrl.set(this.sanitizer.bypassSecurityTrustResourceUrl(this.objectUrl));
          }
        } else {
          this.xml.set(await blob.text());
        }
        this.loading.set(false);
      },
      error: () => { this.loading.set(false); this.error.set(true); },
    });
  }
  async openNativeDocument() {
    this.nativeError.set(null);
    try {
      const result = await documentOpener.open({ base64: this.nativeBase64, mimeType: 'application/pdf', fileName: this.nativeFileName });
      if (result?.saved) this.nativeError.set(`Arquivo salvo em Downloads/Parts ERP: ${result.fileName ?? this.nativeFileName}`);
    } catch (error) {
      this.nativeError.set(error instanceof Error ? error.message : 'Não foi possível abrir o documento.');
    }
  }
  private async openBrowserDocument(invoiceId: string, documentId: string) {
    this.nativeError.set(null);
    try {
      const response = await firstValueFrom(this.api.invoiceDocumentBrowserUrl(invoiceId, documentId));
      if (!response.url) throw new Error('Link do documento não foi gerado.');
      const url = `https://erp.goesautoparts.com.br${response.url}`;
      if (Capacitor.isNativePlatform()) {
        await Browser.open({ url, presentationStyle: 'popover' });
      } else {
        window.open(url, '_blank', 'noopener,noreferrer');
      }
    } catch (error) {
      this.nativeError.set(error instanceof Error ? error.message : 'Não foi possível abrir o navegador.');
    }
  }
  private toBase64(blob: Blob): Promise<string> {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result).split(',', 2)[1] ?? '');
      reader.onerror = () => reject(reader.error);
      reader.readAsDataURL(blob);
    });
  }
  ngOnDestroy() { if (this.objectUrl) URL.revokeObjectURL(this.objectUrl); }
}
