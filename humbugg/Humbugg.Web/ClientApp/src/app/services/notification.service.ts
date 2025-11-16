import { Injectable } from '@angular/core';
import { NotifierService } from 'angular-notifier';

@Injectable({
  providedIn: 'root'
})
export class NotificationService {
  durationInSeconds = 5;

  constructor(private notifierService: NotifierService) { }

  success(message: string) {
    this.notifierService.notify("success", message);
  }

  error(message: string) {
    this.notifierService.notify("error", message);
  }

  default(message: string) {
    this.notifierService.notify("default", message);
  }

  warning(message: string) {
    this.notifierService.notify("warning", message);
  }

  info(message: string) {
    this.notifierService.notify("info", message);
  }
}
