import { Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuthService } from './core/auth.service';
import { PushNotificationsService } from './core/push-notifications.service';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  templateUrl: './app.html',
  styleUrl: './app.scss',
})
export class App {
  private readonly auth = inject(AuthService);
  private readonly pushNotifications = inject(PushNotificationsService);

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.auth.refreshCurrentUser();
      void this.pushNotifications.enableForCurrentDevice();
    }
  }
}
