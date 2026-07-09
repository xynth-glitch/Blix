"use client";

import { useState } from "react";
import { api, type NearbyStop, type Route, type RouteDetails } from "@/lib/api";
import { FreshnessBadge } from "@/components/FreshnessBadge";

export default function Home() {
  const [query, setQuery] = useState("");
  const [routes, setRoutes] = useState<Route[]>([]);
  const [details, setDetails] = useState<RouteDetails | null>(null);
  const [nearby, setNearby] = useState<NearbyStop[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [chatMessage, setChatMessage] = useState("");
  const [chatAnswer, setChatAnswer] = useState<string | null>(null);
  const [chatLoading, setChatLoading] = useState(false);

  async function onSearch() {
    if (!query.trim()) return;
    setError(null);
    setLoading(true);
    setDetails(null);
    try {
      setRoutes(await api.searchRoutes(query.trim()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setLoading(false);
    }
  }

  async function openRoute(routeId: string) {
    setError(null);
    setLoading(true);
    try {
      setDetails(await api.routeDetails(routeId));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load route");
    } finally {
      setLoading(false);
    }
  }

  async function askAssistant() {
    if (!chatMessage.trim()) return;
    setError(null);
    setChatAnswer(null);
    setChatLoading(true);

    const send = async (location?: { lat: number; lon: number } | null) => {
      const response = await api.chat(chatMessage.trim(), location);
      setChatAnswer(response.answer);
    };

    try {
      if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
          (pos) => {
            send({ lat: pos.coords.latitude, lon: pos.coords.longitude })
              .catch((e) =>
                setError(e instanceof Error ? e.message : "Assistant failed")
              )
              .finally(() => setChatLoading(false));
          },
          () => {
            send(null)
              .catch((e) =>
                setError(e instanceof Error ? e.message : "Assistant failed")
              )
              .finally(() => setChatLoading(false));
          },
          { maximumAge: 60_000, timeout: 4000 }
        );
        return;
      }
      await send(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Assistant failed");
    } finally {
      if (!navigator.geolocation) setChatLoading(false);
    }
  }

  function findNearby() {
    setError(null);
    if (!navigator.geolocation) {
      setError("Geolocation is not available in this browser.");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      async (pos) => {
        try {
          setNearby(
            await api.nearbyStops(pos.coords.latitude, pos.coords.longitude)
          );
        } catch (e) {
          setError(e instanceof Error ? e.message : "Failed to load nearby stops");
        }
      },
      () => setError("Could not get your location.")
    );
  }

  return (
    <main className="container">
      <div className="brand">Blix</div>
      <div className="tagline">Think about your destination — not bus routes.</div>

      <div className="section-title">AI travel assistant</div>
      <div className="search">
        <input
          className="input"
          placeholder="Ask: Where is bus 764? Which bus should I take?"
          value={chatMessage}
          onChange={(e) => setChatMessage(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && askAssistant()}
        />
        <button className="btn" onClick={askAssistant} disabled={chatLoading}>
          {chatLoading ? "Thinking…" : "Ask AI"}
        </button>
      </div>
      {chatAnswer && <div className="card"><div className="secondary">{chatAnswer}</div></div>}

      <div className="section-title">Route lookup</div>
      <div className="search">
        <input
          className="input"
          placeholder="Enter a bus route number (e.g. 764)"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && onSearch()}
        />
        <button className="btn" onClick={onSearch} disabled={loading}>
          Search
        </button>
      </div>

      <div style={{ marginTop: 12 }}>
        <button className="btn" onClick={findNearby} style={{ padding: "10px 16px" }}>
          Use my location — find nearby stops
        </button>
      </div>

      {error && <div className="error">{error}</div>}

      {details ? (
        <RouteDetailView details={details} onBack={() => setDetails(null)} />
      ) : (
        <>
          {routes.length > 0 && (
            <>
              <div className="section-title">Routes</div>
              {routes.map((r) => (
                <div
                  key={r.id}
                  className="card"
                  style={{ cursor: "pointer" }}
                  onClick={() => openRoute(r.id)}
                >
                  <div>
                    <div className="primary">
                      {r.short_name || r.long_name || r.id}
                    </div>
                    <div className="secondary">{r.agency_id}</div>
                  </div>
                  <span className="muted">View →</span>
                </div>
              ))}
            </>
          )}

          {nearby.length > 0 && (
            <>
              <div className="section-title">Nearby stops</div>
              {nearby.map((n) => (
                <div key={n.stop.id} className="card">
                  <div>
                    <div className="primary">{n.stop.name}</div>
                    <div className="secondary">Stop {n.stop.code || n.stop.id}</div>
                  </div>
                  <span className="muted">{Math.round(n.distance_m)} m</span>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </main>
  );
}

function RouteDetailView({
  details,
  onBack,
}: {
  details: RouteDetails;
  onBack: () => void;
}) {
  const r = details.route;
  return (
    <>
      <div className="section-title">
        <span style={{ cursor: "pointer" }} onClick={onBack}>
          ← Back
        </span>
      </div>
      <div className="card">
        <div>
          <div className="primary">{r.short_name || r.long_name || r.id}</div>
          <div className="secondary">
            {details.stops.length} stops · {r.agency_id}
          </div>
        </div>
        <span className="muted">
          {details.live_vehicles.length > 0
            ? `${details.live_vehicles.length} live`
            : "no live vehicles"}
        </span>
      </div>

      <div className="section-title">Stop timeline</div>
      {details.stops.map((s) => (
        <div key={`${s.stop.id}-${s.stop_sequence}`} className="card">
          <div>
            <div className="primary">
              {s.stop_sequence}. {s.stop.name}
            </div>
            <div className="secondary">Stop {s.stop.code || s.stop.id}</div>
          </div>
          <FreshnessBadge freshness="scheduled" />
        </div>
      ))}
    </>
  );
}
