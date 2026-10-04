export type QuickDatePreset = 'last7' | 'last30' | 'thisMonth' | 'lastMonth' | 'thisYear' | 'custom';

export const QUICK_DATE_PRESETS: { id: QuickDatePreset; label: string }[] = [
  { id: 'last7', label: '7 dias' },
  { id: 'last30', label: '30 dias' },
  { id: 'thisMonth', label: 'Este mês' },
  { id: 'lastMonth', label: 'Mês passado' },
  { id: 'thisYear', label: 'Este ano' },
  { id: 'custom', label: 'Personalizado' },
];

export interface DateRange {
  startDate: string;
  endDate: string;
}

export function quickDateRange(preset: Exclude<QuickDatePreset, 'custom'>, now = new Date()): DateRange {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12);
  const endDate = formatLocalDate(today);

  if (preset === 'last7' || preset === 'last30') {
    const start = new Date(today);
    start.setDate(start.getDate() - (preset === 'last7' ? 6 : 29));
    return { startDate: formatLocalDate(start), endDate };
  }
  if (preset === 'thisMonth') {
    return { startDate: formatLocalDate(new Date(today.getFullYear(), today.getMonth(), 1, 12)), endDate };
  }
  if (preset === 'lastMonth') {
    return {
      startDate: formatLocalDate(new Date(today.getFullYear(), today.getMonth() - 1, 1, 12)),
      endDate: formatLocalDate(new Date(today.getFullYear(), today.getMonth(), 0, 12)),
    };
  }
  return { startDate: formatLocalDate(new Date(today.getFullYear(), 0, 1, 12)), endDate };
}

function formatLocalDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
