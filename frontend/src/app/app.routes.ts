import { Routes } from '@angular/router';
import { authGuard } from './core/auth.guard';
import { AppLayout } from './layout/app-layout';

export const routes: Routes = [
  // The public catalog is hosted by goesautoparts-site on www. The ERP hostname
  // must open the authenticated application instead of exposing the catalog shell.
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  { path: 'login', loadComponent: () => import('./pages/login/login').then((m) => m.LoginPage) },
  { path: 'document-viewer/:invoiceId/:documentId', loadComponent: () => import('./pages/document-viewer/document-viewer').then((m) => m.DocumentViewerPage), canActivate: [authGuard] },
  {
    path: '',
    component: AppLayout,
    canActivate: [authGuard],
    children: [
      { path: '', pathMatch: 'full', redirectTo: 'dashboard' },
      { path: 'monitoring', loadComponent: () => import('./pages/monitoring/monitoring').then((m) => m.MonitoringPage) },
      { path: 'dashboard', loadComponent: () => import('./pages/dashboard/dashboard').then((m) => m.DashboardPage) },
      { path: 'products', loadComponent: () => import('./pages/products/products').then((m) => m.ProductsPage) },
      { path: 'purchases', loadComponent: () => import('./pages/purchases/purchases').then((m) => m.PurchasesPage) },
      { path: 'finance', loadComponent: () => import('./pages/finance/finance').then((m) => m.FinancePage) },
      { path: 'invoices', loadComponent: () => import('./pages/invoices/invoices').then((m) => m.InvoicesPage) },
      { path: 'customers', loadComponent: () => import('./pages/customers/customers').then((m) => m.CustomersPage) },
      { path: 'marketplace', loadComponent: () => import('./pages/marketplace/marketplace').then((m) => m.MarketplacePage) },
      { path: 'integrations', loadComponent: () => import('./pages/integrations/integrations').then((m) => m.IntegrationsPage) },
      { path: 'users', loadComponent: () => import('./pages/users/users').then((m) => m.UsersPage) },
    ],
  },
  { path: '**', redirectTo: '' },
];
