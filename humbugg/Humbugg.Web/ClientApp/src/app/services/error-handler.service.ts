import { Injectable } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { NotificationService } from '../services/notification.service';

@Injectable({
  providedIn: 'root'
})
export class ErrorHandlerService {

  constructor(private notifyService: NotificationService) { }

  public handleError(error: HttpErrorResponse): void {
    this.notifyService.error(error.error.message);
  }
}
