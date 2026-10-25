import { canAccessPage, UserRole } from '../../core/user-access';

export interface NavigationItem {
  path: string;
  label: string;
  iconPath: string;
}

export interface NavigationSection {
  label: string;
  items: NavigationItem[];
}

export const NAVIGATION_SECTIONS: NavigationSection[] = [
  {
    label: 'Vendas e clientes',
    items: [
      {
        path: '/marketplace',
        label: 'Pedidos online',
        iconPath: 'M4 7l8-4 8 4-8 4-8-4Zm0 0v10l8 4 8-4V7M12 11v10',
      },
      {
        path: '/invoices',
        label: 'Faturas de venda',
        iconPath: 'M6 3.5h9l3 3v14H6zM9 9h6M9 13h6M9 17h3',
      },
      {
        path: '/customers',
        label: 'Clientes',
        iconPath:
          'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
      },
    ],
  },
  {
    label: 'Estoque e compras',
    items: [
      {
        path: '/products',
        label: 'Produtos e estoque',
        iconPath:
          'M20.6 13.6 13.6 20.6a2 2 0 0 1-2.8 0L3 12.8V3h9.8l7.8 7.8a2 2 0 0 1 0 2.8ZM7.5 7.5h.01',
      },
      {
        path: '/purchases',
        label: 'Compras',
        iconPath:
          'M3 4h2l2.4 10.2a2 2 0 0 0 1.9 1.8h7.8a2 2 0 0 0 1.9-1.5L21 8H6M10 20h.01M18 20h.01',
      },
    ],
  },
  {
    label: 'Financeiro',
    items: [
      {
        path: '/finance',
        label: 'Financeiro',
        iconPath: 'M4 19V9M10 19V5M16 19v-7M22 19H2',
      },
      {
        path: '/payables',
        label: 'Contas a pagar',
        iconPath: 'M4 5h16v15H4zM8 3v4M16 3v4M4 10h16M8 14h3',
      },
    ],
  },
  {
    label: 'Análise',
    items: [
      {
        path: '/monitoring',
        label: 'Monitoramento',
        iconPath: 'M3 12h4l2-6 4 12 2-6h6',
      },
      {
        path: '/vehicle-market',
        label: 'Carros no Brasil',
        iconPath: 'M5 17h14l-1.5-6.5A2 2 0 0 0 15.6 9H8.4a2 2 0 0 0-1.9 1.5L5 17ZM4 17v3h3v-2h10v2h3v-3M7 14h.01M17 14h.01',
      },
      {
        path: '/market-studies',
        label: 'Estudos de mercado',
        iconPath: 'M11 18a7 7 0 1 0 0-14 7 7 0 0 0 0 14ZM16 16l5 5',
      },
    ],
  },
];

export const CONFIGURATION_ITEMS: NavigationItem[] = [
  {
    path: '/settings',
    label: 'Geral',
    iconPath: 'M4 7h10M18 7h2M4 17h2M10 17h10M14 4v6M8 14v6',
  },
  {
    path: '/integrations',
    label: 'Integrações',
    iconPath: 'M9 3v5M15 3v5M7 8h10v4a5 5 0 0 1-10 0V8ZM12 17v4',
  },
  {
    path: '/users',
    label: 'Usuários',
    iconPath:
      'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75',
  },
];

export function visibleNavigationSections(role: UserRole | undefined): NavigationSection[] {
  return NAVIGATION_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => canAccessPage(role, item.path)),
  })).filter((section) => section.items.length > 0);
}
