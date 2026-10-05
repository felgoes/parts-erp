import { describe, expect, it } from 'vitest';
import { canAccessPage, ROLE_LABELS } from './user-access';

describe('role-aware page access', () => {
  it('shows operational pages according to the user profile', () => {
    expect(canAccessPage('operator', '/invoices')).toBe(true);
    expect(canAccessPage('operator', '/products')).toBe(true);
    expect(canAccessPage('operator', '/purchases')).toBe(false);
    expect(canAccessPage('stock', '/purchases')).toBe(true);
    expect(canAccessPage('stock', '/finance')).toBe(false);
    expect(canAccessPage('finance', '/finance')).toBe(true);
    expect(canAccessPage('finance', '/users')).toBe(false);
    expect(canAccessPage('viewer', '/invoices?status=cancelled')).toBe(true);
    expect(canAccessPage('viewer', '/integrations')).toBe(false);
  });

  it('restricts user management and credential settings to administrators', () => {
    expect(canAccessPage('admin', '/users')).toBe(true);
    expect(canAccessPage('manager', '/users')).toBe(false);
    expect(canAccessPage('manager', '/integrations')).toBe(false);
    expect(canAccessPage(undefined, '/dashboard')).toBe(false);
  });

  it('uses business-facing profile labels in the interface', () => {
    expect(ROLE_LABELS.operator).toBe('Vendas');
    expect(ROLE_LABELS.stock).toBe('Estoque');
    expect(ROLE_LABELS.finance).toBe('Financeiro');
    expect(ROLE_LABELS.viewer).toBe('Consulta');
  });
});
