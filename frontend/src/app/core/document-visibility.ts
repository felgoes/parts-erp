import { InvoiceDocument } from './models';

export function documentsWithoutXml(documents: InvoiceDocument[]) {
  return documents.filter(
    (doc) => String(doc.document_type || '').trim().toLowerCase() !== 'xml',
  );
}
