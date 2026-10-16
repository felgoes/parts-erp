import { describe, expect, it } from 'vitest';
import { backupAlert, backupStateLabel, backupStateTone } from './backup-health';

describe('estado do backup', () => {
  it('traduz cada estado para o português da tela', () => {
    expect(backupStateLabel('ok')).toBe('Em dia');
    expect(backupStateLabel('late')).toBe('Atrasado');
    expect(backupStateLabel('failed')).toBe('Falhou');
    expect(backupStateLabel('setup_required')).toBe('Configuração pendente');
    expect(backupStateLabel('qualquer_coisa')).toBe('Sem informação');
  });

  it('distingue o tom do estado', () => {
    expect(backupStateTone('ok')).toBe('ok');
    expect(backupStateTone('pending')).toBe('ok');
    expect(backupStateTone('disabled')).toBe('warn');
    expect(backupStateTone('late')).toBe('danger');
    expect(backupStateTone('failed')).toBe('danger');
  });

  it('não gera aviso quando o backup está em dia', () => {
    expect(
      backupAlert({
        backup_state: 'ok',
        backup_last_success_at: '2026-10-16T05:00:00Z',
        backup_last_attempt_at: '2026-10-16T05:00:00Z',
        backup_next_run_at: '2026-10-17T05:00:00Z',
        backup_last_error: null,
      }),
    ).toBeNull();
    expect(backupAlert(null)).toBeNull();
  });

  it('avisa o atraso mesmo quando o último registro foi de sucesso', () => {
    const alert = backupAlert({
      backup_state: 'late',
      backup_last_success_at: '2026-10-14T05:00:00Z',
      backup_last_attempt_at: '2026-10-16T05:00:00Z',
      backup_next_run_at: '2026-10-17T05:00:00Z',
      backup_last_error: null,
    });

    expect(alert?.state).toBe('late');
    expect(alert?.title).toBe('Backup atrasado');
    expect(alert?.detail).toContain('passou do prazo');
  });

  it('mostra o último motivo registrado quando o backup está atrasado', () => {
    const alert = backupAlert({
      backup_state: 'late',
      backup_last_success_at: '2026-10-14T05:00:00Z',
      backup_last_attempt_at: '2026-10-16T14:43:45Z',
      backup_next_run_at: '2026-10-17T05:00:00Z',
      backup_last_error: 'A autorização do Google Drive expirou ou foi revogada.',
    });

    expect(alert?.detail).toContain('passou do prazo');
    expect(alert?.detail).toContain('expirou ou foi revogada');
  });

  it('usa o motivo em português devolvido pelo servidor quando o backup falha', () => {
    const alert = backupAlert({
      backup_state: 'failed',
      backup_last_success_at: '2026-10-14T05:00:00Z',
      backup_last_attempt_at: '2026-10-16T05:00:00Z',
      backup_next_run_at: null,
      backup_last_error: 'A autorização do Google Drive expirou ou foi revogada.',
    });

    expect(alert?.title).toBe('O backup do ERP falhou');
    expect(alert?.detail).toContain('expirou ou foi revogada');
  });
});
