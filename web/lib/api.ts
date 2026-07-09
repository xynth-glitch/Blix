// Typed client for the Blix backend API.
// Types mirror the backend's canonical models (blix/models/canonical.py).

export type Freshness = "live" | "stale" | "scheduled" | "unknown";

export interface Stop {
  id: string;
  code: string | null;
  name: string;
  lat: number;
  lon: number;
  zone_id: string | null;
}

export interface NearbyStop {
  stop: Stop;
  distance_m: number;
}

export interface Route {
  id: string;
  agency_id: string;
  short_name: string | null;
  long_name: string | null;
  route_type: number;
}

export interface StopArrival {
  route_id: string;
  route_name: string;
  trip_id: string | null;
  headsign: string | null;
  eta_seconds: number | null;
  freshness: Freshness;
  vehicle_id: string | null;
}

export interface VehiclePosition {
  vehicle_id: string;
  trip_id: string | null;
  route_id: string | null;
  lat: number;
  lon: number;
  bearing: number | null;
  speed_mps: number | null;
  observed_at: string;
  freshness: Freshness;
}

export interface RouteStop {
  stop: Stop;
  stop_sequence: number;
  scheduled_arrival_s: number | null;
}

export interface RouteDetails {
  route: Route;
  stops: RouteStop[];
  live_vehicles: VehiclePosition[];
}

export interface AssistantLocation {
  lat: number;
  lon: number;
}

export interface AssistantResponse {
  answer: string;
  context: {
    routes: Route[];
    route_details: RouteDetails[];
    nearby_stops: NearbyStop[];
    arrivals: Record<string, StopArrival[]>;
    used_openai: boolean;
  };
}

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return (await res.json()) as T;
}

export const api = {
  nearbyStops: (lat: number, lon: number, radiusM = 500) =>
    get<NearbyStop[]>(
      `/api/stops/nearby?lat=${lat}&lon=${lon}&radius_m=${radiusM}`
    ),
  stopArrivals: (stopId: string) =>
    get<StopArrival[]>(`/api/stops/${encodeURIComponent(stopId)}/arrivals`),
  searchRoutes: (q: string) =>
    get<Route[]>(`/api/routes/search?q=${encodeURIComponent(q)}`),
  routeDetails: (routeId: string) =>
    get<RouteDetails>(`/api/routes/${encodeURIComponent(routeId)}`),
  chat: (message: string, location?: AssistantLocation | null) =>
    post<AssistantResponse>("/api/assistant/chat", { message, location }),
};
