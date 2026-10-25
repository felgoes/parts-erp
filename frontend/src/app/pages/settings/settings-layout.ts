import { Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { AuthService } from '../../core/auth.service';
import { PageHeader } from '../../shared/page-header';

interface SettingsNavItem {
  path: string;
  label: string;
  adminOnly?: boolean;
}

@Component({
  selector: 'app-settings-layout',
  imports: [PageHeader, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './settings-layout.html',
  styleUrl: './settings-layout.scss',
})
export class SettingsLayout {
  private readonly auth = inject(AuthService);
  private readonly items: SettingsNavItem[] = [
    { path: '/settings', label: 'Visão geral' },
    { path: '/settings/identidade', label: 'Identidade' },
    { path: '/settings/empresa', label: 'Empresa', adminOnly: true },
    { path: '/settings/fiscal', label: 'Fiscal', adminOnly: true },
    { path: '/settings/estudo', label: 'Estudo', adminOnly: true },
    { path: '/settings/importacao', label: 'Importação', adminOnly: true },
    { path: '/settings/documentos', label: 'Documentos', adminOnly: true },
    { path: '/settings/aparencia', label: 'Aparência' },
    { path: '/settings/backups', label: 'Backups', adminOnly: true },
    { path: '/settings/ia', label: 'Inteligência artificial', adminOnly: true },
  ];
  readonly navigation = computed(() =>
    this.items.filter(
      (item) => !item.adminOnly || this.auth.user()?.role === 'admin',
    ),
  );
}
