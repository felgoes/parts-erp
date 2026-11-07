import { DatePipe } from '@angular/common';
import {
  Component,
  DestroyRef,
  ElementRef,
  HostListener,
  OnInit,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { debounceTime, filter } from 'rxjs';
import { NotificationHistory } from '../../core/notification-history.service';
import { notificationActions } from '../../core/notification-destination';
import { LiveUpdatesService } from '../../core/live-updates.service';
import { AuthService } from '../../core/auth.service';
import { PushNotification, PushNotificationAction } from '../../core/models';

interface AlertCategory {
  label: string;
  iconPath: string;
}

const CATEGORY_META: Record<string, AlertCategory> = {
  sales: {
    label: 'Venda',
    iconPath: 'M4 7h16v12H4zM8 7V5a4 4 0 0 1 8 0v2M8 12h8',
  },
  order_status: {
    label: 'Pedido',
    iconPath: 'm4 7 8-4 8 4-8 4zM4 7l8 4v10l-8-4zM20 7l-8 4v10l8-4z',
  },
  fiscal: {
    label: 'Fiscal',
    iconPath: 'M6 3.5h9l3 3v14H6zM9 9h6M9 13h6M9 17h3',
  },
  backup: {
    label: 'Backup',
    iconPath:
      'M5 7c0-2 3.1-3.5 7-3.5S19 5 19 7s-3.1 3.5-7 3.5S5 9 5 7Zm0 0v10c0 2 3.1 3.5 7 3.5s7-1.5 7-3.5V7M5 12c0 2 3.1 3.5 7 3.5s7-1.5 7-3.5',
  },
  vehicle_market: {
    label: 'Mercado',
    iconPath: 'M5 17h14l-1.5-6.5A2 2 0 0 0 15.6 9H8.4a2 2 0 0 0-1.9 1.5L5 17ZM4 17v3h3v-2h10v2h3v-3M7 14h.01M17 14h.01',
  },
  system: {
    label: 'Sistema',
    iconPath: 'M12 4 21 20H3zM12 9v5M12 17.5v.5',
  },
};

@Component({
  selector: 'app-notifications-menu',
  imports: [DatePipe, RouterLink],
  templateUrl: './notifications-menu.html',
  styleUrl: './notifications-menu.scss',
})
export class NotificationsMenu implements OnInit {
  readonly feed = inject(NotificationHistory);
  private readonly live = inject(LiveUpdatesService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly host = inject(ElementRef) as ElementRef<HTMLElement>;
  private readonly trigger = viewChild<ElementRef<HTMLButtonElement>>('trigger');
  readonly open = signal(false);
  readonly loading = this.feed.loading;
  readonly history = this.feed.history;
  readonly deleting = this.feed.deleting;
  readonly notificationCount = this.feed.unread;
  readonly preview = computed(() => this.history().slice(0, 4));
  private readonly newSince = signal<string | null>(null);

  ngOnInit(): void {
    this.feed.load();
    this.live.changes$.pipe(debounceTime(250), takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.feed.load(this.open()));
    this.router.events
      .pipe(
        filter((event): event is NavigationEnd => event instanceof NavigationEnd),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe(() => this.open.set(false));
  }

  toggle(): void {
    if (this.open()) {
      this.close(false);
      return;
    }
    this.newSince.set(this.feed.seenAt());
    this.open.set(true);
    this.feed.load(true);
  }

  close(restoreFocus = true): void {
    this.open.set(false);
    if (restoreFocus) requestAnimationFrame(() => this.trigger()?.nativeElement.focus());
  }

  category(item: PushNotification): AlertCategory {
    return CATEGORY_META[item.category] ?? CATEGORY_META['system'];
  }

  actions(item: PushNotification): PushNotificationAction[] {
    return notificationActions(item.data, this.auth.user()?.role);
  }

  isNew(item: PushNotification): boolean {
    const since = this.newSince();
    return !since || item.created_at > since;
  }

  @HostListener('document:pointerdown', ['$event'])
  onDocumentPointerDown(event: PointerEvent): void {
    if (!this.open()) return;
    const target = event.target;
    if (target instanceof Node && !this.host.nativeElement.contains(target)) this.close(false);
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.open()) this.close();
  }

}
