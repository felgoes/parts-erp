export interface ShippingCheckpoint {
  locality: string;
  recorded_at: string | null;
}

export interface ShippingRoute {
  origin: string | null;
  destination: string | null;
  checkpoints: ShippingCheckpoint[];
}
