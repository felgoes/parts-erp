import type { InvoiceDocument } from './models/invoices';

const labels: Record<string, string> = {
  pdf: 'NF',
  xml: 'XML',
  label_pdf: 'Etiqueta',
};

export function documentLabel(value: string | null | undefined): string {
  const normalized = String(value || '')
    .trim()
    .toLowerCase();
  return labels[normalized] || normalized.toUpperCase() || 'Documento';
}

export function invoiceDocumentLabel(doc: InvoiceDocument, documents: InvoiceDocument[]): string {
  const label = doc.document_type === 'pdf' ? 'NF-e' : documentLabel(doc.document_type);
  const sameType = documents.filter((item) => item.document_type === doc.document_type);
  return sameType.length > 1 ? `${label} ${sameType.findIndex((item) => item.id === doc.id) + 1}` : label;
}
