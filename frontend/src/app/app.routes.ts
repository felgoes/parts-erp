import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';
import { accessGuard } from './core/access.guard';
import { AppLayout } from './layout/app-layout';

export const routes: Routes = [
  // The public catalog is hosted by goesautoparts-site on www. The ERP hostname
  // must open the authenticated application instead of exposing the catalog shell.
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  { path: 'login', loadComponent: () => import('./pages/login/login').then((m) => m.LoginPage) },
  {
    path: 'document-viewer/:invoiceId/:documentId',
    loadComponent: () =>
      import('./pages/document-viewer/document-viewer').then((m) => m.DocumentViewerPage),
    canActivate: [authGuard],
  },
  {
    path: '',
    component: AppLayout,
    canActivate: [authGuard, accessGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      {
        path: 'monitoring',
        loadComponent: () => import('./pages/monitoring/monitoring').then((m) => m.MonitoringPage),
      },
      {
        path: 'notifications',
        loadComponent: () =>
          import('./pages/notifications/notifications').then((m) => m.NotificationsPage),
      },
      {
        path: 'dashboard',
        loadComponent: () => import('./pages/dashboard/dashboard').then((m) => m.DashboardPage),
      },
      {
        path: 'products',
        loadComponent: () => import('./pages/products/products').then((m) => m.ProductsPage),
      },
      {
        path: 'purchases',
        loadComponent: () => import('./pages/purchases/purchases').then((m) => m.PurchasesPage),
      },
      {
        path: 'market-studies',
        pathMatch: 'full',
        loadComponent: () =>
          import('./pages/market-studies/market-studies').then((m) => m.MarketStudiesPage),
      },
      {
        path: 'market-studies/new',
        loadComponent: () =>
          import('./pages/market-studies/market-study-new').then((m) => m.MarketStudyNewPage),
      },
      {
        path: 'market-studies/:id',
        loadComponent: () =>
          import('./pages/market-studies/market-study-detail').then(
            (m) => m.MarketStudyDetailPage,
          ),
      },
      {
        path: 'vehicle-market',
        loadComponent: () =>
          import('./pages/vehicle-market/vehicle-market').then((m) => m.VehicleMarketPage),
      },
      {
        path: 'finance',
        loadComponent: () => import('./pages/finance/finance').then((m) => m.FinancePage),
      },
      {
        path: 'payables',
        loadComponent: () => import('./pages/payables/payables').then((m) => m.PayablesPage),
      },
      {
        path: 'invoices',
        loadComponent: () => import('./pages/invoices/invoices').then((m) => m.InvoicesPage),
      },
      {
        path: 'customers',
        loadComponent: () => import('./pages/customers/customers').then((m) => m.CustomersPage),
      },
      {
        path: 'marketplace',
        loadComponent: () =>
          import('./pages/marketplace/marketplace').then((m) => m.MarketplacePage),
      },
      {
        path: 'integrations',
        loadComponent: () =>
          import('./pages/integrations/integrations').then((m) => m.IntegrationsPage),
      },
      {
        path: 'users',
        loadComponent: () => import('./pages/users/users').then((m) => m.UsersPage),
      },
      {
        path: 'settings',
        loadComponent: () =>
          import('./pages/settings/settings-layout').then((m) => m.SettingsLayout),
        children: [
          {
            path: '',
            pathMatch: 'full',
            data: { section: 'home' },
            loadComponent: () =>
              import('./pages/settings/settings').then((m) => m.SettingsPage),
          },
          {
            path: 'identidade',
            data: { section: 'identity' },
            loadComponent: () =>
              import('./pages/settings/settings').then((m) => m.SettingsPage),
          },
          {
            path: 'aparencia',
            data: { section: 'appearance' },
            loadComponent: () =>
              import('./pages/settings/settings').then((m) => m.SettingsPage),
          },
          {
            path: 'backups',
            data: { section: 'backups' },
            loadComponent: () =>
              import('./pages/settings/settings').then((m) => m.SettingsPage),
          },
          {
            path: 'documentos',
            data: { section: 'documents' },
            loadComponent: () =>
              import('./pages/settings/settings').then((m) => m.SettingsPage),
          },
          {
            path: 'empresa',
            data: { tab: 'empresa' },
            loadComponent: () =>
              import('./pages/settings/company-settings').then((m) => m.CompanySettings),
          },
          {
            path: 'fiscal',
            data: { tab: 'fiscal' },
            loadComponent: () =>
              import('./pages/settings/company-settings').then((m) => m.CompanySettings),
          },
          {
            path: 'estudo',
            data: { tab: 'estudo' },
            loadComponent: () =>
              import('./pages/settings/company-settings').then((m) => m.CompanySettings),
          },
          {
            path: 'importacao',
            data: { tab: 'importacao' },
            loadComponent: () =>
              import('./pages/settings/company-settings').then((m) => m.CompanySettings),
          },
          {
            path: 'ia',
            loadComponent: () =>
              import('./pages/settings/settings-ai').then((m) => m.SettingsAi),
          },
        ],
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
