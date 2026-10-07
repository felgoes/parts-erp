const labels: Record<string, string> = {
  pdf: 'NF',
  xml: 'XML',
  label_pdf: 'Etiqueta',
};

export function documentLabel(value: string | null | undefined): string {
  const normalized = String(value || '').trim().toLowerCase();
  return labels[normalized] || normalized.toUpperCase() || 'Documento';
}
