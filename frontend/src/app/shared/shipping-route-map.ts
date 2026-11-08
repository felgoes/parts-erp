import { DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, DestroyRef, ElementRef, Injectable, afterNextRender, computed, inject, input, signal, viewChild } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { catchError, of, shareReplay } from 'rxjs';
import type { ShippingRoute } from '../core/models/shipping-route';

type Point = readonly [x: number, y: number];
type Role = 'origin' | 'stop' | 'destination' | 'latest';
type Pin = { point: Point; role: Role; destination: boolean };
type Position = { x: number; y: number };
interface BrazilMap {
  cities: Record<string, Point | undefined>;
  states: string[];
}

const WIDTH = 640;
const HEIGHT = 300;
let nextMaskId = 0;

function curvedPath(points: Position[]): string {
  if (points.length < 2) return '';
  const [start, ...rest] = points;
  let from = start;
  let path = 'M' + start.x + ',' + start.y;
  for (const [i, to] of rest.entries()) {
    const dx = to.x - from.x;
    const dy = to.y - from.y;
    const length = Math.hypot(dx, dy);
    if (length < 1) continue;
    const bend = Math.min(length * .26, 55) * (i % 2 === 0 ? -1 : 1);
    const ox = -dy * bend / length;
    const oy = dx * bend / length;
    path += ' C' + (from.x + dx / 3 + ox) + ',' + (from.y + dy / 3 + oy)
      + ' ' + (from.x + dx * 2 / 3 + ox) + ',' + (from.y + dy * 2 / 3 + oy)
      + ' ' + to.x + ',' + to.y;
    from = to;
  }
  return from === start ? '' : path;
}

function placeLabels(candidates: { point: Position; text: string; role: Role }[]) {
  const labels: { x: number; y: number; width: number; text: string; role: Role }[] = [];
  for (const { point, text, role } of candidates) {
    const width = Math.min(WIDTH - 20, text.length * 12);
    const x = Math.min(WIDTH - 8 - width / 2, Math.max(8 + width / 2, point.x));
    const offsets = role === 'destination' ? [31, -19, 51] : [-19, 31, -38];
    const y = offsets.map((dy) => point.y + dy).find((cy) => cy > 19 && cy < HEIGHT - 8 &&
      !labels.some((other) => Math.abs(cy - other.y) < 24 && Math.abs(x - other.x) < (width + other.width) / 2));
    if (y !== undefined) labels.push({ x, y, width, text, role });
  }
  return labels;
}

function localityKey(locality: string): string {
  const stateSeparator = locality.lastIndexOf(',');
  const city = locality.slice(0, stateSeparator);
  const uf = locality.slice(stateSeparator + 1).trim().toUpperCase();
  return city.normalize('NFD').toLowerCase().replace(/[^a-z0-9]/g, '') + ',' + uf;
}

@Injectable({ providedIn: 'root' })
class ShippingMapData {
  readonly map$ = inject(HttpClient).get<BrazilMap>('geo/shipping-brazil-v1.json').pipe(
    shareReplay(1),
  );
}

@Component({
  selector: 'app-shipping-route-map',
  imports: [DatePipe],
  templateUrl: './shipping-route-map.html',
  styleUrl: './shipping-route-map.scss',
})
export class ShippingRouteMap {
  readonly route = input<ShippingRoute | null>(null);
  readonly status = input.required<string>();
  readonly maskId = 'shipping-route-reveal-' + nextMaskId++;
  readonly motion = signal<'static' | 'waiting' | 'playing'>('static');
  private readonly mapFrame = viewChild.required<ElementRef<HTMLElement>>('mapFrame');
  private readonly destroyRef = inject(DestroyRef);
  private readonly data = toSignal(inject(ShippingMapData).map$.pipe(catchError(() => of(null))));
  readonly loading = computed(() => this.data() === undefined);
  readonly latest = computed(() => this.route()?.checkpoints.at(-1));

  constructor() {
    afterNextRender(() => {
      if (typeof IntersectionObserver === 'undefined' ||
          matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      this.motion.set('waiting');
      const observer = new IntersectionObserver((entries) => {
        if (!entries.some((entry) => entry.intersectionRatio >= 0.2)) return;
        this.motion.set('playing');
        observer.disconnect();
      }, { threshold: 0.2 });
      observer.observe(this.mapFrame().nativeElement);
      this.destroyRef.onDestroy(() => observer.disconnect());
    });
  }

  readonly drawing = computed(() => {
    const data = this.data();
    if (!data) return null;
    const route = this.route();
    const find = (locality: string | null | undefined) =>
      locality ? data.cities[localityKey(locality)] : undefined;
    const origin = find(route?.origin);
    const destination = find(route?.destination);
    const stops = route?.checkpoints.map((checkpoint) => find(checkpoint.locality)) ?? [];
    const latest = stops.at(-1);
    const track = [origin, ...stops, destination].filter((point): point is Point => !!point);
    const extent = track.length ? track : [[-74, -6], [-34, 34]];
    const xs = extent.map(([x]) => x);
    const ys = extent.map(([, y]) => y);
    const spanX = Math.max(...xs) - Math.min(...xs);
    const spanY = Math.max(...ys) - Math.min(...ys);
    const scale = Math.min((WIDTH - 120) / Math.max(3.6, spanX), (HEIGHT - 100) / Math.max(2.4, spanY));
    const tx = WIDTH / 2 - scale * (Math.min(...xs) + spanX / 2);
    const ty = HEIGHT / 2 - scale * (Math.min(...ys) + spanY / 2);
    const project = ([x, y]: Point): Position => ({ x: x * scale + tx, y: y * scale + ty });

    const pins = new Map<string, Pin>();
    const pointKey = (point: Point) => point.join(',');
    const pin = (point: Point | undefined, role: Role) => {
      if (!point) return;
      const key = pointKey(point);
      pins.set(key, { point, role, destination: role === 'destination' || !!pins.get(key)?.destination });
    };
    stops.forEach((point) => pin(point, 'stop'));
    pin(origin, 'origin');
    pin(destination, 'destination');
    pin(latest, 'latest');

    const reported = [origin, ...stops].filter((point): point is Point => !!point);
    const nextStart = latest ?? (stops.length ? undefined : origin);
    const pending = destination && nextStart ? [nextStart, destination].map(project) : [];
    const label = (point: Point | undefined, text: string | null | undefined, role: Role) =>
      point && text ? [{ point: project(point), text, role }] : [];
    const isDestination = (point: Point | undefined) =>
      !!(point && destination && pointKey(point) === pointKey(destination));

    return {
      states: data.states,
      transform: 'translate(' + tx + ',' + ty + ') scale(' + scale + ')',
      confirmed: curvedPath(reported.map(project)),
      pending: curvedPath(pending),
      pins: [...pins.values()].map(({ point, role, destination }) => ({ ...project(point), role, destination })),
      labels: placeLabels([
        ...label(destination, route?.destination, 'destination'),
        ...(!isDestination(latest) ? label(latest, this.latest()?.locality, 'latest') : []),
        ...(!isDestination(origin) && origin !== latest ? label(origin, route?.origin, 'origin') : []),
      ]),
      latestMapped: !!latest,
      destinationMapped: !!destination,
      hasPins: pins.size > 0,
    };
  });
}
