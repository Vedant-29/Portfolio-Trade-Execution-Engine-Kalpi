# Portfolio Trade Execution Engine

A containerized FastAPI service and React frontend that authenticates
with an Indian stock broker, executes a target portfolio (first-time
or rebalance) in a single click, and surfaces typed results.

<p>
  <em>Submitted for the</em> <strong>Kalpi Builder Assignment</strong>
  <em>by</em> <a href="https://www.kalpicapital.com/"><em>Kalpi Capital</em></a>.
  &nbsp;·&nbsp;
  <a href="./Kalpi%20Builder%20Assignment.pdf">Original brief (PDF)</a>
</p>

> **Live-test status**
> Only the **Zerodha** adapter has been exercised end-to-end against a
> real broker account. The other five adapters (Upstox, AngelOne, Fyers,
> Groww, Paytm Money) are code-complete and registered at startup, but
> their live flows were not exercised: broker-account KYC and developer-
> app approvals for those accounts were still pending when this was
> submitted. The adapter pattern is identical across all six; plugging
> valid credentials into `.env` should work without code changes.

## Demo

A short end-to-end walkthrough — broker connect → payload upload →
execute → results + history.

<video
  src="https://github.com/vedantagarwal/Portfolio-Trade-Execution-Engine-Kalpi/raw/main/docs/demo.mp4"
  controls
  width="720">
  Your browser does not support the video tag.
  <a href="./docs/demo.mp4">Download the demo video</a>
</video>

---

## Table of contents

1. [What this builds](#what-this-builds)
2. [Architecture](#architecture)
3. [Persistence](#persistence)
4. [Notifications and logging](#notifications-and-logging)
5. [Adding a new broker](#adding-a-new-broker)
6. [Setup](#setup)
7. [Repository tour](#repository-tour)
8. [Credits](#credits)

---

## What this builds

A single-click portfolio trade execution engine. The user picks a
broker, authenticates via the broker's own auth flow, uploads a list
of target holdings, and the service places every order on the real
broker API.

Two execution modes are supported:

- **First-time portfolio** — BUY each item in the list.
- **Rebalancing** — the payload explicitly tells the engine what to
  SELL, what new symbols to BUY, and which existing holdings to ADJUST
  (by a positive or negative quantity delta). Orders run in the
  **SELL → BUY_NEW → ADJUST** sequence so that sell proceeds free up
  cash before the next BUY.

Supported order types: `CNC` (delivery) and `MIS` (intraday square-off).
Price types: `MARKET` and `LIMIT`. Both regular and **after-market
orders (AMO)** are supported — when the market is closed, the UI
auto-switches the payload template to a LIMIT-shaped example (Zerodha
AMO requires LIMIT) and validates before submission.

Failures are contained per-order: one rejected order never kills the
batch. Errors are typed and classified (insufficient funds, market
closed, IP not whitelisted, circuit limit, etc.) and surfaced with
human-readable labels in the UI.

## Architecture

Layered backend; small centered React frontend.

```
 Frontend  (React · TanStack Query · shadcn/ui)
    │
    ▼
 FastAPI routes  ─┬─►  Services   (Auth · Execution · Notification)
                  │
                  └─►  Adapters   (one folder per broker · strict ABC)
                          │
                          ▼
                       Broker SDK / REST
```

**Each broker adapter lives in `src/adapters/{broker}/` as two files:**

| File | Responsibility |
|---|---|
| `adapter.py` | Broker-specific auth flow (OAuth redirect / credentials form / API-key only) and order placement, subclassing the common `BrokerAdapter` ABC. |
| `mapping.py` | Small translation tables between canonical enums (`Action`, `Exchange`, `PriceType`, `ProductType`) and the broker's wire values. |

**Canonical schemas** in `src/schemas/` — `orders.py`, `portfolio.py`,
`session.py`, `holdings.py` — define the single vocabulary that every
layer outside the adapters speaks. The adapters are the only place that
knows about any given broker's quirks.

Adding a new broker does **not** require touching the schema layer: the
`BrokerSession.extras` dict absorbs broker-specific overflow without a
schema change.

## Persistence

Two independent tables in a single SQLite file (one Docker volume
mount covers both):

| Table | Purpose |
|---|---|
| `sessions` | Broker access tokens, encrypted at rest with Fernet. Survives page refreshes and container restarts — the user doesn't re-authenticate every time they come back. |
| `execution_events` | Every trade summary (broker, mode, placed count, failed count, per-order detail). Surfaced in the **History** tab of the frontend, which auto-polls every 15 seconds. |

## Notifications and logging

Deliberately simple:

- Every execution emits one clean `execution_summary` line on stdout
  (structured logs via `structlog`; noisy access-log polls are
  silenced so the signal is readable).
- The same summary is persisted to the SQLite events table and made
  queryable through `GET /events`.
- No webhook, email, or WebSocket. The assignment allowed any of those
  options, but terminal logs plus the History tab give the reviewer
  two reliable surfaces with no external dependencies.

## Adding a new broker

The adapter pattern is designed so that a sixth (or seventh, or Nth)
broker requires minimal code changes. To make that concrete, the repo
ships with a Claude Code skill that automates the scaffold:

```
.claude/skills/add-broker/
```

Invoking `/add-broker` inside Claude Code with a broker name and its
developer-docs URL produces `adapter.py`, `mapping.py`, the `__init__.py`
wiring, and all config / registry / `.env.example` edits in one pass.

**Paytm Money** (the sixth adapter in this repo) was added using this
skill as a dogfooding exercise, which caught a few small gaps in the
templates that were then fixed.

## Setup

### Prerequisites

- **Docker Desktop** for the containerized path, **or**
- **Python 3.11+** with [`uv`](https://docs.astral.sh/uv/) and
  [`pnpm`](https://pnpm.io/) for the local dev path.

### 1. Clone and prepare environment

```bash
git clone https://github.com/vedantagarwal/Portfolio-Trade-Execution-Engine-Kalpi.git
cd Portfolio-Trade-Execution-Engine-Kalpi
cp .env.example .env
```

`.env.example` ships with a working `FERNET_KEY` (used to encrypt
broker access tokens at rest on disk). The app runs immediately
after the copy — no key-generation step required. Replace the value
with `make fernet-key` for a real deployment; the bundled default is
sufficient for this take-home.

### 2. Add at least one broker's credentials

Open `.env` and fill in the API key and secret for whichever broker(s)
you want to test:

```
<BROKER>_API_KEY=<your key>
<BROKER>_API_SECRET=<your secret>
```

For each broker, the steps to obtain these credentials — creating the
developer app, setting the redirect URL, whitelisting your public IP
(SEBI mandate for all broker APIs since April 2026) — follow the same
pattern across the industry.

We reference the excellent
[**OpenAlgo documentation on connecting brokers**](https://docs.openalgo.in/connect-brokers/brokers)
as a single guide for that setup. Their guide covers the
developer-app creation flow, callback URL, and IP whitelist steps for
every broker we support here.

> **Note on OpenAlgo:** we use OpenAlgo only as a documentation
> reference for broker onboarding. This codebase does **not** depend
> on, fork, or reuse any OpenAlgo platform code. All adapters here
> are original implementations against each broker's official SDK
> (or documented REST endpoints where no SDK exists).

Any broker whose credentials are missing from `.env` simply appears
as "Not configured" on the UI — the app still runs.

### 3. Run the app

**Recommended — Docker, one command:**

```bash
make up
# equivalent: docker compose up --build
```

Then open **<http://localhost:8000>**. Backend and the built frontend
are served from the same container.

**Alternative — local dev loop with hot reload on both sides:**

```bash
make install    # uv sync + pnpm install  (one-time)
make dev-all    # starts uvicorn :8000 and vite :5173 in parallel
```

Open <http://localhost:5173> for the frontend. Vite proxies API calls
to the backend on `:8000`.

### 4. Common Make targets

| Target | What it does |
|---|---|
| `make up` | Build and run the Docker stack |
| `make down` | Stop the Docker stack |
| `make logs` | Tail the container's structured log output |
| `make rebuild` | Full no-cache rebuild (use if you changed the Dockerfile) |
| `make test` | Run the Python test suite (106 tests) |
| `make lint` | `ruff check` over the backend code |
| `make dev-all` | Run backend and frontend in parallel, hot-reloading |
| `make fernet-key` | Generate a fresh Fernet key |

Every `make` target is an alias for the equivalent `docker compose` or
`uv` command. If you prefer typing the raw commands (for example on
Windows without `make`), each is a one-liner; `make -n <target>` prints
the underlying command.

## Repository tour

| Path | Purpose |
|---|---|
| [`Kalpi Builder Assignment.pdf`](./Kalpi%20Builder%20Assignment.pdf) | Original assignment brief |
| [`src/schemas/`](./src/schemas/) | Canonical shapes — orders, portfolio, sessions, holdings |
| [`src/adapters/`](./src/adapters/) | One folder per broker (`zerodha`, `upstox`, `angelone`, `fyers`, `groww`, `paytm`) plus `BrokerAdapter` base class and error taxonomy |
| [`src/services/`](./src/services/) | Auth, execution, notification |
| [`src/api/`](./src/api/) | FastAPI routes |
| [`src/storage/`](./src/storage/) | SQLite-backed session and event stores |
| [`frontend/`](./frontend/) | React app — single centered page, 4-step wizard, History tab |
| [`Dockerfile`](./Dockerfile), [`docker-compose.yml`](./docker-compose.yml) | One-command deployment |
| [`.claude/skills/add-broker/`](./.claude/skills/add-broker/) | Claude skill that scaffolds a new broker adapter |

## Credits

- [**OpenAlgo**](https://docs.openalgo.in/) — referenced throughout for
  broker-onboarding documentation (developer-app setup, callback URLs,
  IP whitelisting). Their docs are the clearest consolidated reference
  for the Indian broker-API landscape. This project does not use
  OpenAlgo's platform, code, or SDK — the reference is documentation
  only.
- Official broker SDKs — `kiteconnect` (Zerodha, MIT),
  `upstox-python-sdk` (Apache 2.0), `smartapi-python` (AngelOne, MIT),
  `fyers-apiv3` (MIT), `growwapi` (MIT).
