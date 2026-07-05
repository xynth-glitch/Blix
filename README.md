# Blix

«The AI-Powered Public Transport Companion»

Blix is an AI-powered mobility platform built to modernize public transportation by making it smarter, faster, and easier to use. Instead of forcing commuters to manually search routes, timings, and bus information, Blix combines real-time transit data with artificial intelligence to provide personalized travel assistance.

Our goal is to reduce uncertainty while commuting and help people make better travel decisions every day.

---

# Vision

Public transportation should be as intelligent and effortless as using a ride-hailing app.

Blix aims to become the AI layer for public transport by providing commuters with live information, intelligent recommendations, and a seamless travel experience across cities.

---

# Current Development Scope

The first version of Blix focuses on the Delhi Transport Ecosystem, including:

- Delhi Transport Corporation (DTC)
- Delhi Integrated Multi-Modal Transit System (DIMTS)
- Cluster Bus Services
- Public bus routes operating within Delhi

The platform is being designed so that additional cities and transport authorities can be integrated in the future without major architectural changes.

---

# Core Features

Real-Time Bus Tracking

- Live vehicle locations
- Bus movement visualization
- Estimated arrival times
- Route progress
- Delay information (where available)

---

# Smart Route Planning

Users can enter:

- Current location
- Destination

Blix will recommend:

- Best available route
- Fastest route
- Minimum walking route
- Minimum transfers
- Alternative routes
- Estimated travel duration

---

# AI Travel Assistant

Instead of only displaying data, Blix explains it.

Examples:

- Which bus should I take?
- Is it worth waiting?
- Should I change buses?
- Is another route faster?
- Which stop should I get off at?

The assistant provides natural-language recommendations based on available transit information.

---

# Nearby Bus Stops

Users can:

- Discover nearby bus stops
- View walking distance
- View buses serving each stop
- Navigate directly to the stop

---

# Bus Information

For every supported bus:

- Route number
- Origin
- Destination
- Intermediate stops
- Operating status
- Route map

---

# Live Arrival Estimates

Users can view:

- Next arriving buses
- Estimated arrival times
- Route information
- Destination details

---

# Personalized Experience

Future personalization may include:

- Favorite routes
- Saved destinations
- Home and workplace shortcuts
- Frequently used buses
- Daily commute suggestions

---

# Design Principles

Blix is built around five principles:

- Simplicity
- Speed
- Accuracy
- Accessibility
- AI-first user experience

Every feature should reduce commuter effort rather than add complexity.

---

# Technology Goals

The platform is designed around:

- Modern frontend architecture
- Scalable backend services
- Real-time data processing
- AI-powered decision assistance
- Map integration
- Location services
- Secure authentication
- Cloud deployment

---

# Long-Term Roadmap

Planned future capabilities include:

- Metro integration
- Multi-modal journey planning
- Traffic-aware routing
- Service disruption alerts
- AI commute predictions
- Voice assistant support
- Smart notifications
- Offline trip support
- Digital transport passes (where supported)
- City expansion across India

---

# Target Users

Blix is designed for:

- Daily commuters
- Students
- Office workers
- Tourists
- First-time public transport users
- Senior citizens

---

# Project Status

Current Phase: Active Development

The project is under continuous development. Features, architecture, and user experience will evolve as additional capabilities and transport systems are integrated.

---

# Mission

To make public transportation intelligent, reliable, and accessible through AI, helping millions of commuters travel with confidence.

---

# License

No open-source license has been applied to this repository. All rights are reserved. The source code, assets, and documentation may not be copied, modified, or redistributed without explicit permission from the project owner.
---

# Engineering Guide

> The sections below cover the technical implementation, repository layout, and local setup for the Phase 1 foundation.

**AI-powered public transport assistant — think about your destination, not bus routes.**

Blix turns government buses into a ride-hailing-grade experience. Phase 1 targets
**Delhi government buses** (DTC + DIMTS) using the official
[Open Transit Data (OTD)](https://otd.delhi.gov.in) feeds.

> Design principle: a **deterministic transport engine** is the correctness core.
> The AI layer (added later) is only a *consumer* of this engine and never a source
> of transit facts. Real-time values always carry a **freshness** label so scheduled
> data is never presented as live.

See [`docs/phase-0-understanding.md`](docs/phase-0-understanding.md) for the full
product analysis, architecture rationale, risks, and roadmap.

## Repository layout

```
blix/
  backend/          FastAPI + deterministic transport engine (Python)
    blix/
      models/       canonical domain model + SQLAlchemy ORM (PostGIS)
      providers/    TransitProvider interface + Delhi OTD adapter
      ingestion/    static GTFS importer + real-time VehiclePositions poller
      engine/       nearby stops, route details, arrivals, fares, freshness
      api/          HTTP API (thin layer over the engine)
      cli.py        operational CLI (init-db, import-static, poll-rt)
  web/              Next.js web app (destination-first UI)
  infra/            docker-compose (PostGIS)
  docs/             Phase 0 understanding & architecture
```

## What's implemented (Phase 1a/1b foundation)

- Canonical, provider-agnostic transit model (GTFS-shaped) + provider abstraction.
- Delhi OTD adapter: static GTFS download + GTFS-Realtime `VehiclePositions` parsing.
- Postgres + PostGIS schema; chunked importer for the real Delhi feed
  (~2.4k routes, ~10.6k stops, ~3.7M stop_times, ~2.3M fare rules).
- Real-time poller writing latest-per-vehicle **and** an append-only history
  warehouse (so future ETA/delay models have data from day one).
- Engine + API: nearby stops (PostGIS), route details + stop timeline + live
  vehicles, scheduled arrivals board, fare lookup, feed health/freshness.
- Next.js web shell: route search, route timeline, nearby stops, freshness badges.

Not yet built (by design — see roadmap): journey planning (OTP2 + custom ETA),
the AI assistant layer, and the map UI.

## Quick start

### 1. Database
```bash
docker compose -f infra/docker-compose.yml up -d
```

### 2. Backend
```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env            # adjust if needed

blix init-db                    # create PostGIS extension + tables
blix import-static              # download + import the Delhi static GTFS
# blix import-static --dir /path/to/extracted/gtfs   # or use a local bundle

uvicorn blix.main:app --reload  # http://localhost:8000/docs
```

### 3. Real-time (optional — requires an OTD key)
Register at <https://otd.delhi.gov.in/data/realtime/> to obtain a private key,
set `BLIX_OTD_REALTIME_KEY` in `.env`, then:
```bash
blix poll-rt                    # continuous poller
# or a single fetch:
blix poll-once
```

### 4. Web
```bash
cd web
npm install
cp .env.local.example .env.local
npm run dev                     # http://localhost:3000
```

## Development
```bash
# backend
cd backend && ruff check . && mypy blix && pytest -q
# web
cd web && npm run typecheck && npm run lint && npm run build
```
