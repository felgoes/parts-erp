import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { apiUrl } from '../api-url';
import { FleetOverview, FleetRecordPage } from '../models/fleet';
import { queryParams } from './http-helpers';

@Injectable({ providedIn: 'root' })
export class FleetApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('/fleet');

  overview(params: Record<string, string | number> = {}): Observable<FleetOverview> {
    return this.http.get<FleetOverview>(`${this.base}/overview`, {
      params: queryParams(params),
    });
  }

  records(params: Record<string, string | number> = {}): Observable<FleetRecordPage> {
    return this.http.get<FleetRecordPage>(`${this.base}/records`, {
      params: queryParams(params),
    });
  }
}
