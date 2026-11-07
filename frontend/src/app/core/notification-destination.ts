import { PushNotificationAction } from './models';
import { canAccessPage, UserRole } from './user-access';

const SALE_EVENTS = new Set(['sale', 'ready_to_ship', 'order_status']);
const OTHER_ROUTES = new Set(['/marketplace', '/settings', '/fleet', '/notifications']);
const ID = /^[a-z0-9][a-z0-9-]{0,79}$/i;
const UNAVAILABLE = { route: '/notifications', query: { aviso: 'venda-indisponivel' } };

export function notificationDestination(data: Record<string, unknown>, role: UserRole | undefined): Omit<PushNotificationAction, 'label'> {
  const type = typeof data['type'] === 'string' ? data['type'] : '';
  if (SALE_EVENTS.has(type)) {
    const id = data['invoice_id'];
    return typeof id === 'string' && ID.test(id) && canAccessPage(role, '/invoices')
      ? { route: '/invoices/' + id, query: { alerta: '1' } }
      : UNAVAILABLE;
  }

  const route = data['route'];
  if (typeof route !== 'string' || !OTHER_ROUTES.has(route) || !canAccessPage(role, route)) {
    return { route: '/notifications' };
  }
  const orderId = data['marketplace_order_id'];
  if (route === '/marketplace' && typeof orderId === 'string' && ID.test(orderId)) {
    return { route, query: { order_id: orderId } };
  }
  return { route };
}

export function notificationActions(data: Record<string, unknown>, role: UserRole | undefined): PushNotificationAction[] {
  const type = typeof data['type'] === 'string' ? data['type'] : '';
  const sale = SALE_EVENTS.has(type);
  const destination = notificationDestination(data, role);
  const actions: PushNotificationAction[] = sale
    ? [{ label: destination.route === '/notifications' ? 'Ver aviso' : 'Abrir venda', ...destination }]
    : [];
  if (!Array.isArray(data['actions'])) return actions;

  for (const action of data['actions']) {
    if (typeof action?.label !== 'string' || typeof action.route !== 'string') continue;
    if (sale && action.route === '/marketplace') continue;
    const documentPath = action.route.split('/');
    const document = documentPath.length === 4 && documentPath[1] === 'document-viewer'
      && !documentPath[0] && ID.test(documentPath[2]) && ID.test(documentPath[3]);
    if (!(document ? canAccessPage(role, '/invoices')
      : OTHER_ROUTES.has(action.route) && canAccessPage(role, action.route))) continue;
    const orderId = action.query?.order_id;
    const query = action.route === '/marketplace' && typeof orderId === 'string' && ID.test(orderId)
      ? { order_id: orderId }
      : undefined;
    actions.push({ label: action.label, route: action.route, query });
  }
  return actions;
}
