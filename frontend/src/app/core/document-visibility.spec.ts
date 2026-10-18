import { describe, expect, it } from 'vitest';
import { documentsWithoutXml } from './document-visibility';

describe('document visibility', () => {
  it('keeps PDFs and labels while omitting XML files', () => {
    const documents = [
      { id: '1', document_type: 'pdf', filename: 'nota.pdf', created_at: '' },
      { id: '2', document_type: 'xml', filename: 'nota.xml', created_at: '' },
      { id: '3', document_type: 'label_pdf', filename: 'etiqueta.pdf', created_at: '' },
    ];

    expect(documentsWithoutXml(documents).map((doc) => doc.id)).toEqual(['1', '3']);
  });

  it('recognizes the XML type regardless of case or surrounding spaces', () => {
    const documents = [
      { id: '1', document_type: ' XML ', filename: 'nota.xml', created_at: '' },
      { id: '2', document_type: 'pdf', filename: 'nota.pdf', created_at: '' },
    ];

    expect(documentsWithoutXml(documents).map((doc) => doc.id)).toEqual(['2']);
  });
});
