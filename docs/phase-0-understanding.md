# Blix — Phase 0: Project Understanding & Architecture Document

**Author:** Devin (engineering)
**Status:** Analysis / pre-implementation
**Scope:** Understand the product, assess feasibility, propose architecture, identify risks, recommend structure & build order, surface gaps.

---

## 1. Product understanding (restated for alignment)

Blix is an **AI-powered public-transport assistant** whose north star is:

> *People should think about their destination — not about bus routes.*

It is **not** a bus-tracker. It is a decision assistant that ingests official transit data (static + real-time), reasons over it, and answers a commuter's real question: *"How do I get where I'm going, right now, with the least confusion?"*

The product test for every feature is: **"Does this reduce confusion for the commuter?"** If not, cut it.

**Phase 1 target:** Delhi Government buses (DTC/DIMTS), because Delhi publishes official developer datasets (GTFS static + GTFS-Realtime). Architecture must make **multi-city + multimodal (metro/train/auto)** expansion cheap.

**Non-negotiable AI principle:** the AI must never invent transport facts. It reasons only over verified data + user context, and says "I don't know" when data is missing. **Reliability > sounding confident.**

---

## 2. The single most important reality check (read this first)

Almost every promised feature depends on **one external variable: the quality and availability of Delhi's real-time bus feed.**

- **Static GTFS** (routes, stops, trips, schedules, fares) for Delhi (OTD — Open Transit Data, otd.delhi.gov.in) is generally reliable and complete enough to build 70% of the product.
- **GTFS-Realtime (vehicle positions)** is the make-or-break dependency. In practice Indian city RT feeds are **partial** (not every bus is GPS-equipped/online), **laggy** (10–30s+), and **occasionally down**. Coverage varies by fleet (DTC vs cluster buses).

**Consequence:** features that assume "we always know exactly where every bus is" (live tracking, "should I wait for this bus?", per-stop ETA for every stop) are only as good as this feed. **The architecture must treat real-time position as *probabilistic and frequently absent*, not as ground truth.** This single decision shapes the whole system.

Everything below is designed around that reality.

---

## 3. Feature-by-feature feasibility review

Legend: **Feasible** (Phase 1) · **Feasible w/ caveats** · **Hard / defer**.

### 3.1 AI Destination Search — *Feasible w/ caveats* (this is the flagship)
Input: current location + destination → ranked journey options (nearby stops, buses, ETA, walk distance, total time, transfers, fare).

- This is fundamentally a **journey-planning / routing problem** over a transit graph — **not** primarily an "AI" problem. The heavy lifting is a **routing engine** (RAPTOR / CSA algorithm, or OpenTripPlanner / Valhalla). The "AI" is a thin natural-language + ranking layer on top.
- **Caveat 1 — geocoding:** "India Gate" → lat/lng requires a geocoder (Google Places, Mapbox, or self-hosted Nominatim/Photon). Cost & rate limits matter.
- **Caveat 2 — ranking "intelligently":** ranking needs a defined objective (time vs transfers vs fare vs reliability). Define this explicitly; don't hand-wave it to an LLM.
- **Caveat 3 — fare:** Delhi bus fare is largely **distance/slab-based** and depends on AC/non-AC. Computable from static data with a fare model; verify against official fare rules.
- **Verdict:** the highest-value and highest-effort feature. Build the routing engine as the core; the LLM only translates language ↔ structured query and explains results.

### 3.2 Live Bus Tracking — *Feasible w/ caveats*
Enter route number → live position, current/next stop, direction, full stop timeline, remaining stops, per-stop ETA.

- Static parts (route direction, full stop list/timeline) are **fully feasible** from GTFS static.
- Live position + per-stop ETA are **only as good as GTFS-RT**. Must degrade gracefully: when RT is stale/absent, fall back to **scheduled** times and clearly label them ("scheduled, not live").
- Per-stop ETA requires **map-matching** the vehicle to the route shape and estimating travel time along remaining segments (using average segment speeds / historical data later).

### 3.3 Nearby Buses (GPS) — *Feasible w/ caveats*
Show nearby buses with destination, ETA, distance, fare, route.

- "Nearby stops" and "which routes serve them" = trivial from static data + a spatial index.
- "Nearby **buses**" (actual vehicles near me) again depends on RT coverage. Recommend framing as **"buses arriving at stops near you"** (arrivals board), which is robust even with partial RT, rather than "vehicles physically near you" which looks broken when RT is sparse.

### 3.4 AI Travel Assistant (NL Q&A) — *Feasible w/ caveats*
"Which bus should I take?", "Fastest/cheapest?", "Can I reach before 5?", "Should I wait?"

- Implement as **tool-calling / function-calling over the transport engine**, NOT free generation. The LLM's job: parse intent → call `planJourney`, `getArrivals`, `getFare`, etc. → narrate the structured result.
- **"Can I reach before 5 PM?"** and **"Should I wait for this bus?"** are the riskiest — they require confident ETA predictions. Answer conservatively with ranges and confidence, and refuse when RT/data is insufficient. This directly enforces the "never invent" principle.
- Guardrail: the model must be **forbidden from stating any number** (ETA, fare, stop) that didn't come from a tool result.

### 3.5 Route Details — *Feasible* (map, stop timeline, position, route stats)
- Map + stop timeline + route stats: feasible now. Live position: RT-dependent.
- **Average delay** and **reliability score** are explicitly future — and they require **collecting our own historical RT snapshots over time** (see §7). Start logging RT from day one so these become possible later.

### 3.6 Future features (crowd, delay prediction, accessibility, favorites, notifications, boarding reminders, offline, voice, multicity)
- **Favorites, notifications, boarding reminders, offline caching of static data, voice input** — straightforward later, low risk.
- **Delay prediction & crowd estimation** — ML features requiring a historical data pipeline; feasible *only if we start warehousing RT now*.
- **Multicity/multimodal** — an architecture concern, handled by the provider abstraction in §5.

---

## 4. Recommended architecture (with improvements over the proposed stack)

The proposed layering (Presentation → Business Logic → Transport Engine → AI → Data → Official APIs) is directionally right. Two important corrections:

1. **AI is not a layer beneath business logic — it's a *client* of the Transport Engine.** The AI should sit *beside* the business logic and call the same transport-engine services the UI does. If AI is a lower layer that everything passes through, you couple correctness to an unreliable component. Invert it: **deterministic engine at the core, AI as an optional consumer.**
2. **Insert an explicit Data Ingestion & Normalization layer** between official APIs and the engine. Raw feeds are messy, versioned, and city-specific; normalize once into a canonical model.

### 4.1 Proposed layers

```
                ┌─────────────────────────────────────────┐
   Clients      │  Web app / Mobile (Presentation)          │
                └───────────────┬───────────────────────────┘
                                │  REST/GraphQL + WebSocket (live)
                ┌───────────────▼───────────────────────────┐
   API Gateway  │  BFF / API layer (auth, rate-limit, cache) │
                └───────┬───────────────────────┬────────────┘
                        │                        │
         ┌──────────────▼─────────┐   ┌──────────▼───────────────┐
         │  Transport Engine       │   │  AI Assistant Service     │
         │  (DETERMINISTIC core)   │◄──│  (LLM + tool-calling;     │
         │  - journey planner      │   │   ONLY calls the engine)  │
         │  - arrivals / ETA       │   └───────────────────────────┘
         │  - fare calc            │
         │  - geocoding facade     │
         └──────────┬──────────────┘
                    │  canonical transit model
         ┌──────────▼──────────────────────────────────────┐
         │  Data layer:  Static store (GTFS)  +  RT store    │
         │  (Postgres+PostGIS, Redis for live, spatial idx)  │
         └──────────┬───────────────────────────────────────┘
                    │
         ┌──────────▼──────────────────────────────────────┐
         │  Ingestion & Normalization                        │
         │  (GTFS static importer + GTFS-RT poller →         │
         │   canonical model; provider adapters per city)    │
         └──────────┬───────────────────────────────────────┘
                    │
         ┌──────────▼──────────────────────────────────────┐
         │  Provider Adapters (abstract):                    │
         │  Delhi OTD ▸ future: Metro ▸ Rail ▸ other cities  │
         └──────────────────────────────────────────────────┘
```

### 4.2 Key design decisions & rationale

- **Deterministic core, AI as consumer.** Correctness (routing, fares, ETAs) lives in testable, deterministic code. The LLM only translates language and narrates. This is the concrete implementation of "AI never invents."
- **Provider abstraction (`TransitProvider` interface).** Every city/mode implements the same interface (`getStatic()`, `getVehiclePositions()`, `getTripUpdates()`, geocode, fare rules). Delhi is the first implementation. Multicity = add an adapter, not a rewrite.
- **Canonical transit model.** Normalize to GTFS-like entities (Agency, Route, Stop, Trip, StopTime, Shape, Vehicle, Fare) so the engine is provider-agnostic. GTFS is the natural canonical schema — the ecosystem already standardizes on it.
- **Two-speed data store:**
  - *Static* (routes/stops/trips/fares): Postgres + **PostGIS** (spatial queries for nearby stops), refreshed when the agency publishes a new GTFS bundle.
  - *Real-time* (vehicle positions/trip updates): **Redis** (or in-memory) with short TTL, updated by the RT poller; also **appended to a time-series/warehouse** for future ML.
- **RT freshness is first-class.** Every RT-derived value carries a timestamp + `freshness` status (`live` / `stale` / `scheduled`). The UI and AI must surface this. Never present scheduled data as live.
- **Routing engine:** don't hand-roll graph search first. Evaluate **OpenTripPlanner (OTP2)** — it consumes GTFS + GTFS-RT directly and does multimodal routing out of the box. Building RAPTOR/CSA yourself is a valid v2 optimization but a poor use of Phase 1 time. (Decision to confirm — see §9.)
- **Stateless services + horizontal scale.** Engine and AI services stateless; state in Postgres/Redis. Enables scaling and caching.

### 4.3 Suggested tech stack (proposal, to confirm with user)
- **Backend:** TypeScript/Node (Nest/Fastify) *or* Python (FastAPI). Python is attractive for the future ML (delay prediction); Node is attractive for one-language full-stack. **Recommend Python/FastAPI for the engine + ML path, or Node if team prefers single language.**
- **DB:** PostgreSQL + PostGIS; Redis for live/cache.
- **Routing:** OpenTripPlanner 2 (self-hosted) as the planner, wrapped by our engine facade.
- **Frontend:** React (Next.js) web first; React Native later for the "cab-like" mobile experience the vision implies.
- **Maps:** MapLibre GL + a tile provider (Mapbox/self-host); geocoding via Photon/Nominatim (self-host to control cost) or a paid geocoder.
- **AI:** an LLM with **strict tool-calling**; no free-form transport claims.

---

## 5. Technical risks (ranked)

| # | Risk | Impact | Mitigation |
|---|------|--------|-----------|
| 1 | **GTFS-RT coverage/quality poor or feed goes down** | Core live features look broken | Design for graceful degradation to scheduled data; explicit freshness labels; frame "nearby buses" as arrivals; monitor feed uptime/coverage as a health metric |
| 2 | **ETA accuracy** ("can I reach by 5?", "should I wait?") | Wrong answers destroy trust | Conservative ranges + confidence; refuse when data insufficient; improve via historical model later; never a single false-precise number |
| 3 | **LLM hallucinating transport facts** | Violates core principle, unsafe advice | Tool-calling only; model may not emit numbers not from tools; response validation layer; automatic "I don't know" path |
| 4 | **Data licensing / API access & rate limits (OTD keys, geocoder, map tiles)** | Blocks build / surprise cost | Confirm OTD API key + terms early; cache aggressively; self-host geocoding/tiles where licensing allows |
| 5 | **Fare correctness** | Users mistrust wrong fares | Encode official fare rules explicitly; validate against published fare table; label estimates |
| 6 | **GTFS static drift** (agency republishes, IDs change) | Broken routes/stops | Versioned imports, validation on import, alerting on schema/coverage changes |
| 7 | **Geocoding ambiguity** ("India Gate" vs many matches) | Wrong journeys | Disambiguation UI; bias to city bounds; confidence threshold |
| 8 | **Cost & latency of LLM on every query** | Slow, expensive | Use LLM only where NL is needed; deterministic path for structured UI actions; cache; small model for intent parsing |
| 9 | **Scope creep from "future" list** | Phase 1 never ships | Strict gate: "does it reduce confusion *now*?"; future items only influence design, not scope |
| 10 | **No historical data = no delay/reliability later** | Future features impossible | **Start warehousing RT snapshots from day 1** even though the feature is future |

---

## 6. Recommended project structure

Monorepo, clear module boundaries mirroring the layers:

```
blix/
  apps/
    web/                  # Next.js frontend
    api/                  # BFF / API gateway (REST + WebSocket)
  services/
    transport-engine/     # deterministic: planner, arrivals, ETA, fare
    ai-assistant/         # LLM tool-calling; depends on engine client only
    ingestion/            # GTFS static importer + GTFS-RT poller
  packages/
    core-model/           # canonical transit types (shared)
    providers/            # TransitProvider interface + adapters
      delhi-otd/          # first implementation
    fare-engine/          # fare rule models
    geo/                  # geocoding facade, spatial utils
    config/ , logger/ , testing/
  infra/                  # docker-compose, migrations, IaC, OTP config
  data/                   # sample GTFS for local dev/tests
```

Principles: UI never imports transport logic directly (only via API); AI depends on the engine's **client interface**, never on raw data; providers are swappable; everything provider-agnostic above the adapter boundary.

---

## 7. Recommended development order

**Phase 1a — Foundations (data first, no UI features yet)**
1. Repo scaffold, canonical model, `TransitProvider` interface.
2. Delhi OTD adapter: import **static GTFS** into Postgres+PostGIS; validate.
3. **RT poller**: ingest GTFS-RT → Redis + append to warehouse (start collecting history immediately).
4. Feed health monitoring (coverage %, staleness).

**Phase 1b — Deterministic engine (the real product core)**
5. Nearby stops + arrivals board (works even with partial RT). ← *first user-visible value*
6. Route details: full stop timeline + live position w/ freshness labels.
7. Journey planning (integrate OTP2 or CSA/RAPTOR) → ranked options with time/transfers/walk.
8. Fare engine → attach fare to journeys & routes.

**Phase 1c — AI layer (thin, on top of a working engine)**
9. Tool-calling assistant wrapping engine services; strict "no invented facts" guardrails + response validation.
10. NL destination search → structured query → ranked results; conservative ETA answers.

**Phase 1d — Product polish**
11. Minimal/premium UI, map UX, disambiguation, error/empty/stale states.
12. Favorites/notifications (if time) — else defer.

**Cross-cutting from day 1:** tests on the deterministic engine, RT history warehousing, observability, freshness/labeling discipline.

Rationale: **data → deterministic correctness → AI → polish.** The AI is built last on purpose, so it always has a reliable engine to call. The first shippable slice (arrivals board) delivers value without depending on perfect RT.

---

## 8. Missing requirements, edge cases & open questions

**Missing / underspecified requirements**
- **Success metrics:** what defines a "good" ranked result? (time vs transfers vs fare vs reliability weighting.) Needs a product decision.
- **Auth/accounts:** anonymous vs login? Needed for favorites/notifications/history.
- **Offline expectations:** static data can be cached offline; RT cannot. Define the offline promise.
- **Accessibility:** stated as future but affects data model (wheelchair-accessible stops/vehicles in GTFS) — capture the fields now.
- **Localization:** Delhi implies Hindi + English (and Hinglish NL queries). Plan for it in the AI + UI.
- **Legal/data terms:** OTD usage terms, attribution, geocoder & map-tile licensing, LLM data-privacy for user locations.
- **Privacy:** user location is sensitive — retention policy, consent, anonymization for the warehouse.

**Edge cases to design for**
- RT feed empty/stale/down → scheduled fallback + clear labeling.
- Bus that already passed the stop ("has it passed?") — a core user question; needs direction + last-seen position logic.
- Last bus of the day / no service at this hour → "no buses now; next at …".
- Destination unreachable by bus alone → require walk legs / suggest transfer / say so.
- Ambiguous or out-of-city destination.
- Route with multiple directions/variants; loop routes.
- Split/short-turn trips; detours & service alerts (GTFS-RT `Alerts`).
- Vehicle GPS jitter / off-route points → map-matching + outlier rejection.
- Fare with AC vs non-AC, free-travel schemes (e.g. women's free bus travel in Delhi) — surface correctly.
- Very long journeys / many transfers → cap and rank sensibly.
- Clock/timezone/DST correctness for schedules (IST).

**Open questions for the user (need answers before 1b)**
1. Confirmed access to **Delhi OTD API key** + which datasets (static only, or static + RT)? Any usage terms we must honor?
2. Preferred **stack**: Python/FastAPI (better ML path) vs Node/TypeScript (single language)?
3. OK to adopt **OpenTripPlanner 2** for routing, or do you want a custom RAPTOR/CSA engine?
4. **Ranking objective**: default to fastest, or expose fastest/cheapest/fewest-transfers toggles from day 1?
5. Web-first or mobile-first for Phase 1? (Vision implies mobile "cab-like" UX eventually.)
6. Which **LLM provider** / any self-hosting or data-residency constraints for user location data?
7. Budget posture for **geocoding + map tiles** (self-host vs paid)?
8. Auth in Phase 1 (needed for favorites/notifications) or fully anonymous?

---

## 8b. Delhi OTD investigation — findings (verified against otd.delhi.gov.in)

I inspected the official portal (Dept. of Transport, Govt of NCT of Delhi, with IIIT-Delhi). Confirmed facts:

**Access model**
- **Static GTFS:** publicly downloadable as a `.zip` (a short "purpose" form gates the download, but no key needed).
- **Real-time:** requires **registration** (name, email, phone, company, description) → they issue a **private API key**. Endpoint: `GET /api/realtime/VehiclePositions.pb?key=YOUR_PRIVATE_KEY` (GTFS-Realtime **protobuf**).
- **DMRC (Metro) static data** is also published → good for future multimodal.
- Use is governed by OTD Terms & Conditions (must accept/attribute).

**What the data actually contains — I downloaded and inspected the real feed** (GTFS.zip, ~55 MB, dated **June 2024**). Verified contents:

| file | rows | notes |
|------|------|-------|
| agency.txt | 2 | **DTC** + **DIMTS** (cluster buses) |
| routes.txt | 2,403 | all `route_type=3` (bus); note: `route_short_name` is largely blank, `route_long_name` holds the number+direction e.g. `828AUP` |
| stops.txt | 10,559 | has `stop_lat/lon`, `zone_id` |
| trips.txt | 89,393 | **`shape_id` column exists but every value is blank** |
| stop_times.txt | 3,724,320 | `arrival/departure/stop_id/stop_sequence` |
| calendar.txt | **1** | single service, all 7 days, `20240101–20250101` |
| fare_attributes.txt | 2,305,138 | price in INR, per fare_id |
| fare_rules.txt | 2,305,138 | keyed by `route_id, origin_id, destination_id` |

**Corrected findings (some better, some worse than the docs implied):**

1. **Fares ARE included — and richly.** Contrary to the documentation, the bundle ships a full **origin→destination fare matrix** (~2.3M `fare_rules` mapping stop-pair → price via `zone_id`). *Good news:* we don't have to reverse-engineer fare slabs for the base case. *Caveat:* 2.3M rows is large — needs indexed storage (Postgres), and we should still layer official schemes on top (AC vs non-AC, women's free "pink ticket") that a static matrix won't encode.

2. **No route geometry at all.** `shapes.txt` is absent **and** `trips.shape_id` is blank. Impact stands: **route/vehicle map geometry and ETA-along-route must be derived ourselves** by map-matching stop sequences to the road network (OSRM/Valhalla). This is confirmed, not hypothetical.

3. **Weak, stale service calendar.** Just **one** `calendar` entry (every day, no weekend/holiday variation), **no `calendar_dates`**, and it **expires 2025-01-01** while the bundle is dated mid-2024. Impact: (a) no service-day nuance to rely on; (b) the static bundle may be **refreshed infrequently and can be stale** — treat versioning/freshness of the *static* feed as a monitored risk, not just the RT feed.

4. **Schedule times are explicitly unreliable.** The portal warns stop_times are *"not accurate ... a rough estimate generated by assuming a constant speed of travel."* Impact: **we cannot trust the timetable for ETAs.** ETA quality rests on real-time + our own modeling — making **RT warehousing from day 1 essential**, not optional.

5. **Real-time = VehiclePositions only.** No `TripUpdates`, no `Alerts` documented. The feed gives **raw GPS positions, not predicted arrivals**. We compute trip progress + per-stop ETA ourselves (map-match vehicle → route → segment-speed ETA; heuristic first, historical model later). This is the crux of the product's accuracy.

**Scale note for design:** ~2.4k routes, ~10.6k stops, ~89k trips, ~3.7M stop_times, ~2.3M fare rules → comfortably a Postgres+PostGIS job with proper indexing; not "toy" data, but not big-data either.

**Effect on the routing-engine decision:** OpenTripPlanner 2 derives its real-time arrivals mainly from GTFS-RT **TripUpdates**, which Delhi does **not** provide — so OTP's realtime benefit here is limited. OTP2 is still excellent for **static/schedule journey planning** (multimodal, transfers), but the **live ETA layer must be custom** (VehiclePositions → map-match → ETA) regardless of engine choice.

---

## 8c. Finalized recommendations (decisions you delegated to me)

- **OTD access (Q1): confirmed & already validated.** I downloaded and inspected the real static GTFS (see §8b) — it's usable today, no key required. Real-time (VehiclePositions) needs a **one-time registration** for a private key. **Recommendation:** submit the RT registration early (authorisation may take time). *I need one input from you before registering: the name/email/phone/company/description to submit — I won't send your personal details without approval.* Also note the static bundle I pulled is dated mid-2024 with a calendar expiring Jan 2025, so we should check for a fresher bundle when we start ingestion.
- **Backend stack (Q2): Python + FastAPI.** Rationale: (a) the accuracy path is fundamentally an **ML/data problem** (ETA from historical RT, delay prediction) where Python's ecosystem dominates; (b) mature GTFS/geo libs (`gtfs-kit`/`partridge`, `gtfs-realtime-bindings`, `shapely`, `geopandas`, OSRM/Valhalla clients); (c) FastAPI gives async + typed APIs. Frontend stays **Next.js/TypeScript** (Q4: web-first) — one boundary (the API), two languages, which is fine.
- **Routing engine (Q3): Hybrid.** Use **OpenTripPlanner 2 for static journey planning** (fast to stand up, handles transfers/multimodal, ready for Metro later), wrapped behind our engine facade; build a **custom real-time ETA service** (VehiclePositions → map-match → segment-speed ETA) because Delhi provides no TripUpdates. If OTP proves heavy to operate, fall back to a RAPTOR/CSA library — but not a from-scratch algorithm in Phase 1.
- **Platform (Q4): Web-first, Next.js.** Confirmed. Keep API/UI decoupled so a React Native app can reuse the same API later.

---

## 9. Summary recommendation

Blix is feasible and compelling, but its quality is **bounded by the real-time feed**, so the architecture must treat live position as probabilistic and degrade gracefully. Build a **deterministic transport engine as the core**, make the **AI a strict tool-calling consumer** of that engine (never a source of facts), abstract **providers** for multicity/multimodal growth, and **start warehousing real-time data from day 1** to unlock delay/reliability/crowd features later. Ship value early with an **arrivals board**, layer journey planning + fares, then add the AI, then polish the UI. Before implementation, get answers to the eight open questions in §8 — especially **OTD access, stack choice, and routing-engine choice**.
