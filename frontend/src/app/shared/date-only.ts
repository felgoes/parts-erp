/**
 * Calendar dates (previsão de entrega, data do documento) have no timezone:
 * they are stored as UTC midnight and must never be shifted by the local zone.
 */

export function dateOnlyLabel(value: string | null | undefined): string {
  const part = dateOnlyValue(value);
  if (!part) return '';
  const [year, month, day] = part.split('-');
  return year && month && day ? `${day}/${month}/${year}` : part;
}

export function dateOnlyValue(value: string | null | undefined): string {
  if (!value) return '';
  return value.slice(0, 10);
}
