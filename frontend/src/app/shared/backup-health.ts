/**
 * Estado do backup automático (P16): rótulo em português e o texto do aviso.
 *
 * O backend devolve o estado calculado pelo último sucesso — `late` quando o backup bom
 * ficou velho, mesmo que o último registro gravado tenha sido de sucesso.
 */

export interface BackupSnapshot {
  backup_state: string;
  backup_last_success_at: string | null;
  backup_last_attempt_at: string | null;
  backup_next_run_at: string | null;
  backup_last_error: string | null;
}

export interface BackupAlert {
  state: string;
  title: string;
  detail: string;
}

const STATE_LABELS: Record<string, string> = {
  setup_required: 'Configuração pendente',
  disabled: 'Backup desligado',
  pending: 'Aguardando o primeiro backup',
  ok: 'Em dia',
  failed: 'Falhou',
  late: 'Atrasado',
};

export function backupStateLabel(state: string | null | undefined): string {
  return STATE_LABELS[String(state ?? '')] ?? 'Sem informação';
}

export function backupStateTone(state: string | null | undefined): 'ok' | 'warn' | 'danger' {
  if (state === 'late' || state === 'failed') return 'danger';
  if (state === 'setup_required' || state === 'disabled') return 'warn';
  return 'ok';
}

/** Aviso para a faixa do ERP e para o cartão do backup; `null` quando não há o que avisar. */
export function backupAlert(snapshot: BackupSnapshot | null | undefined): BackupAlert | null {
  if (!snapshot) return null;
  if (snapshot.backup_state === 'late') {
    return {
      state: 'late',
      title: 'Backup atrasado',
      detail: snapshot.backup_last_success_at
        ? 'O último backup concluído passou do prazo esperado. Confira a conexão com o Drive e rode um backup agora.'
        : 'Nenhum backup foi concluído ainda. Confira a conexão com o Drive e rode um backup agora.',
    };
  }
  if (snapshot.backup_state === 'failed') {
    return {
      state: 'failed',
      title: 'O backup do ERP falhou',
      detail:
        snapshot.backup_last_error ||
        'O último backup não foi concluído. Abra os backups para ver o motivo e reconectar a conta.',
    };
  }
  return null;
}
