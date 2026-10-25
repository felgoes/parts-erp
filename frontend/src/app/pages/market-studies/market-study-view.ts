const DECISION_LABELS: Record<string, string> = {
  recomendada_para_teste: 'Recomendada para teste',
  negociar_fornecedor: 'Negociar fornecedor',
  validar_demanda: 'Validar demanda',
  observar: 'Observar',
  rejeitada: 'Rejeitada',
  dados_insuficientes: 'Dados insuficientes',
};

export function decisionLabel(value: string | null | undefined): string {
  return DECISION_LABELS[value ?? ''] ?? 'Em triagem';
}

export function trendWidth(value: number, rows: Array<{ value: number }>): number {
  const maximum = Math.max(...rows.map((row) => row.value), 1);
  return Math.round((value / maximum) * 100);
}
