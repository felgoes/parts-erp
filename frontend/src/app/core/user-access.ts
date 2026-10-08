import { User } from './models';

export type UserRole = User['role'];

export const ROLE_LABELS: Record<UserRole, string> = {
  admin: 'Administrador',
  manager: 'Gerente',
  operator: 'Vendas',
  stock: 'Estoque',
  finance: 'Financeiro',
  viewer: 'Consulta',
};

export const ROLE_DESCRIPTIONS: Record<UserRole, string> = {
  admin: 'Acesso completo, incluindo usuários, integrações e credenciais.',
  manager: 'Administra a operação e os cadastros, sem gerenciar usuários ou credenciais.',
  operator: 'Atende clientes e registra vendas; sem ajustes de estoque ou dados de custo.',
  stock: 'Cuida de estoque, recebimentos e devoluções; sem acesso a custos e financeiro.',
  finance: 'Consulta custos, compras e indicadores financeiros; não altera a operação.',
  viewer: 'Consulta os registros e indicadores, sem executar alterações.',
};

const PAGE_ROLES: Record<string, UserRole[]> = {
  dashboard: ['admin', 'manager', 'operator', 'stock', 'finance', 'viewer'],
  monitoring: ['admin', 'manager', 'viewer'],
  notifications: ['admin', 'manager', 'viewer'],
  products: ['admin', 'manager', 'operator', 'stock', 'finance', 'viewer'],
  purchases: ['admin', 'manager', 'stock', 'finance', 'viewer'],
  'market-studies': ['admin', 'manager', 'finance', 'viewer'],
  finance: ['admin', 'manager', 'finance', 'viewer'],
  invoices: ['admin', 'manager', 'operator', 'stock', 'finance', 'viewer'],
  customers: ['admin', 'manager', 'operator', 'finance', 'viewer'],
  marketplace: ['admin', 'manager', 'operator', 'stock', 'finance', 'viewer'],
  integrations: ['admin'],
  users: ['admin'],
  settings: ['admin'],
};

export function canAccessPage(role: UserRole | undefined, url: string): boolean {
  if (!role) return false;
  const page = url.split('?')[0].split('/').filter(Boolean)[0] || 'dashboard';
  return PAGE_ROLES[page]?.includes(role) ?? false;
}

export function canManageUsers(role: UserRole | undefined): boolean {
  return role === 'admin';
}

export function canManageCatalog(role: UserRole | undefined): boolean {
  return role === 'admin' || role === 'manager';
}

export function canAdjustStock(role: UserRole | undefined): boolean {
  return canManageCatalog(role) || role === 'stock';
}

export function canReadCosts(role: UserRole | undefined): boolean {
  return role === 'admin' || role === 'manager' || role === 'finance' || role === 'viewer';
}

export function canSell(role: UserRole | undefined): boolean {
  return canManageCatalog(role) || role === 'operator';
}

export function canManagePurchases(role: UserRole | undefined): boolean {
  return canManageCatalog(role);
}
