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
import { filter } from 'rxjs';
import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { PushNotification } from '../../core/models';

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
  private readonly api = inject(ApiService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly destroyRef = inject(DestroyRef);
  private readonly host = inject(ElementRef) as ElementRef<HTMLElement>;
  private readonly trigger = viewChild<ElementRef<HTMLButtonElement>>('trigger');
  readonly open = signal(false);
  readonly loading = signal(false);
  readonly history = signal<PushNotification[]>([]);
  readonly notificationCount = signal(0);
  readonly preview = computed(() => this.history().slice(0, 4));
  private readonly newSince = signal<string | null>(null);

  ngOnInit(): void {
    this.load();
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
    this.newSince.set(this.notificationsSeenAt());
    this.open.set(true);
    this.load(true);
  }

  close(restoreFocus = true): void {
    this.open.set(false);
    if (restoreFocus) requestAnimationFrame(() => this.trigger()?.nativeElement.focus());
  }

  category(item: PushNotification): AlertCategory {
    return CATEGORY_META[item.category] ?? CATEGORY_META['system'];
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

  private load(markSeen = false): void {
    this.loading.set(true);
    this.api.pushHistory().subscribe({
      next: (items) => {
        this.history.set(items);
        if (markSeen) {
          this.markNotificationsSeen(items);
          this.notificationCount.set(0);
          return;
        }
        const seenAt = this.notificationsSeenAt();
        this.notificationCount.set(
          items.filter((item) => !seenAt || item.created_at > seenAt).length,
        );
      },
      error: () => this.history.set([]),
      complete: () => this.loading.set(false),
    });
  }

  private notificationsSeenAt(): string | null {
    const userId = this.auth.user()?.id;
    return userId ? localStorage.getItem(`parts-erp.notifications.seen.${userId}`) : null;
  }

  private markNotificationsSeen(items: PushNotification[]): void {
    const userId = this.auth.user()?.id;
    const latest = items[0]?.created_at;
    if (userId && latest) localStorage.setItem(`parts-erp.notifications.seen.${userId}`, latest);
  }
}
