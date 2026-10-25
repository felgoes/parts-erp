import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { apiUrl } from '../api-url';
import {
  CnpjCardParse,
  CompanyProfile,
  CompanyProfileData,
} from '../models/company-profile';

@Injectable({ providedIn: 'root' })
export class CompanyApi {
  private readonly http = inject(HttpClient);
  private readonly base = apiUrl('/settings/company');

  profile(): Observable<CompanyProfile> {
    return this.http.get<CompanyProfile>(this.base);
  }

  save(
    revision: number,
    data: CompanyProfileData,
    manualFields: string[],
  ): Observable<CompanyProfile> {
    return this.http.put<CompanyProfile>(this.base, {
      revision,
      data,
      manual_fields: manualFields,
    });
  }

  parseCard(file: File): Observable<CnpjCardParse> {
    const body = new FormData();
    body.append('file', file, file.name);
    return this.http.post<CnpjCardParse>(`${this.base}/cnpj-card/parse`, body);
  }

  history(): Observable<
    Array<{
      id: string;
      revision: number;
      changed_fields: string[];
      changed_by: string | null;
      created_at: string;
    }>
  > {
    return this.http.get<
      Array<{
        id: string;
        revision: number;
        changed_fields: string[];
        changed_by: string | null;
        created_at: string;
      }>
    >(`${this.base}/history`);
  }
}
