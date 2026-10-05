const API_ORIGIN = 'https://erp.goesautoparts.com.br';

export function apiUrl(path: string): string {
  const base = typeof window !== 'undefined' && (window.location.protocol === 'capacitor:' || (window.location.hostname === 'localhost' && window.location.port === ''))
    ? `${API_ORIGIN}/api/v1`
    : '/api/v1';
  const suffix = path ? (path.startsWith('/') ? path : `/${path}`) : '';
  return `${base}${suffix}`;
}
