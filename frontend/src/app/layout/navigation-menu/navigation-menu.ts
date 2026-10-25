import {
  Component,
  DestroyRef,
  ElementRef,
  OnInit,
  computed,
  inject,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive } from '@angular/router';
import { filter } from 'rxjs';
import { AuthService } from '../../core/auth.service';
import { CONFIGURATION_ITEMS, visibleNavigationSections } from './navigation';

@Component({
  selector: 'app-navigation-menu',
  imports: [RouterLink, RouterLinkActive],
  templateUrl: './navigation-menu.html',
  styleUrl: './navigation-menu.scss',
})
export class NavigationMenu implements OnInit {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  readonly closeRequested = output<void>();
  readonly settingsOpen = signal(false);
  readonly sections = computed(() => visibleNavigationSections(this.auth.user()?.role));
  readonly isAdmin = computed(() => this.auth.user()?.role === 'admin');
  readonly configurationItems = CONFIGURATION_ITEMS;
  private readonly configurationActive = signal(false);
  private readonly adminSection = viewChild<ElementRef<HTMLElement>>('adminSection');

  ngOnInit(): void {
    this.syncConfiguration(this.router.url);
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((event) => this.syncConfiguration(event.urlAfterRedirects));
  }

  isConfigurationActive(): boolean {
    return this.configurationActive();
  }

  toggleSettings(): void {
    const open = !this.settingsOpen();
    this.settingsOpen.set(open);
    if (open) this.revealAdminSection();
  }

  private syncConfiguration(url: string): void {
    const route = url.split('?')[0].replace(/^\//, '');
    const active =
      route === 'settings' ||
      route.startsWith('settings/') ||
      ['integrations', 'users'].includes(route);
    this.configurationActive.set(active);
    this.settingsOpen.set(active);
    if (active) this.revealAdminSection();
  }

  private revealAdminSection(): void {
    requestAnimationFrame(() =>
      this.adminSection()?.nativeElement.scrollIntoView({ block: 'nearest' }),
    );
  }
}
