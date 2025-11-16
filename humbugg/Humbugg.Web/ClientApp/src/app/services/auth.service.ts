import { Injectable, Inject } from '@angular/core';
import { BehaviorSubject, Observable } from 'rxjs';
import { HttpClient } from '@angular/common/http';
import { tap } from 'rxjs/operators';
import { DOCUMENT } from '@angular/common';

@Injectable({
    providedIn: 'root'
})
export class AuthService {
    private _isUserAuthenticatedSubject = new BehaviorSubject<boolean>(false);
    isUserAuthenticated: Observable<boolean> = this._isUserAuthenticatedSubject.asObservable();

    constructor(@Inject(DOCUMENT) private document: Document, private httpClient: HttpClient) { }

    updateUserAuthenticationStatus() {
        return this.httpClient
            .get<boolean>(`/auth/isAuthenticated`, { withCredentials: true })
            .pipe(tap(isAuthenticated => {
                this._isUserAuthenticatedSubject.next(isAuthenticated);
            }));
    }

    setUserAsNotAuthenticated() {
        this._isUserAuthenticatedSubject.next(false);
    }

    login(returnUrl: string) {
        var url = `/auth/signin`;
        if (returnUrl) {
            url += `?returnUrl=${returnUrl}`;
        }
        this.document.location.href = url;
    }

    logout() {
        this.document.location.href = '/auth/signout';
    }
}