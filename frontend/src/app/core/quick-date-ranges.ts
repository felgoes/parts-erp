export type QuickDatePreset =
  'today' | 'last7' | 'last30' | 'thisMonth' | 'lastMonth' | 'thisYear' | 'custom';

export const QUICK_DATE_PRESETS: { id: QuickDatePreset; label: string }[] = [
  { id: 'today', label: 'Hoje' },
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

export function quickDateRange(
  preset: Exclude<QuickDatePreset, 'custom'>,
  now = new Date(),
): DateRange {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate(), 12);
  const endDate = preset === 'today' ? saoPauloDate(now) : formatLocalDate(today);
  if (preset === 'today') return { startDate: endDate, endDate };

  if (preset === 'last7' || preset === 'last30') {
    const start = new Date(today);
    start.setDate(start.getDate() - (preset === 'last7' ? 6 : 29));
    return { startDate: formatLocalDate(start), endDate };
  }
  if (preset === 'thisMonth') {
    return {
      startDate: formatLocalDate(new Date(today.getFullYear(), today.getMonth(), 1, 12)),
      endDate,
    };
  }
  if (preset === 'lastMonth') {
    return {
      startDate: formatLocalDate(new Date(today.getFullYear(), today.getMonth() - 1, 1, 12)),
      endDate: formatLocalDate(new Date(today.getFullYear(), today.getMonth(), 0, 12)),
    };
  }
  return { startDate: formatLocalDate(new Date(today.getFullYear(), 0, 1, 12)), endDate };
}

export function matchingDatePreset(startDate: string, endDate: string): QuickDatePreset {
  return QUICK_DATE_PRESETS.find(({ id }) => {
    if (id === 'custom') return false;
    const range = quickDateRange(id);
    return range.startDate === startDate && range.endDate === endDate;
  })?.id ?? 'custom';
}

function saoPauloDate(date: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Sao_Paulo', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(date);
  const value = (type: string) => parts.find((part) => part.type === type)?.value ?? '';
  return value('year') + '-' + value('month') + '-' + value('day');
}

function formatLocalDate(date: Date): string {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`;
}
