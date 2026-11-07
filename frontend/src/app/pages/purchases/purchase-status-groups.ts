import type { PurchaseStatus } from '../../core/models';

export const PURCHASE_GROUPS = [
  { value: 'preparation', label: 'Em preparação', states: ['negotiating', 'approved'] },
  { value: 'receiving', label: 'A receber', states: ['ordered', 'partially_received'] },
  { value: 'finished', label: 'Finalizada', states: ['received', 'closed'] },
  { value: 'cancelled', label: 'Cancelada', states: ['cancelled'] },
] satisfies { value: string; label: string; states: PurchaseStatus[] }[];

export function purchaseGroup(status: PurchaseStatus) {
  return PURCHASE_GROUPS.find((group) => (group.states as PurchaseStatus[]).includes(status))!;
}
