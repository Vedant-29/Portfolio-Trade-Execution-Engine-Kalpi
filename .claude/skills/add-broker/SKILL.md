---
name: add-broker
description: Scaffold a new Indian broker adapter end-to-end — creates the
  adapter folder (adapter.py, mapping.py, __init__.py), wires it into
  the config, registry, and .env.example, and prints the exact
  follow-up steps. Use this whenever the user asks to "add a new
  broker" / "support Dhan" / "wire up Paytm Money" etc.
---

# Add a new broker adapter

This skill automates the mechanical parts of adding a 6th (or 7th, or
Nth) broker to the Portfolio Trade Execution Engine. It is the
reusable productization of the "Adapter Pattern — adding a 6th broker
requires minimal code changes" requirement from the original
assignment brief.

## When to invoke

The user said something like:

- "add support for Dhan"
- "wire up Paytm Money"
- "I want to test with 5paisa, add the adapter"
- "scaffold a new broker called MirrorOne"

Any of those. The skill runs once per new broker.

## What this skill will do

Given a new broker spec, it produces a complete, working scaffold:

1. **Gathers the broker spec** — either from the user's initial message
   or by asking a concise set of questions.
2. **Fetches reference material** — the broker's official SDK surface
   (primary source) and OpenAlgo's reference implementation if the
   broker is supported there (secondary source, for quirks).
3. **Generates files**:
   - `src/adapters/{name}/__init__.py`
   - `src/adapters/{name}/adapter.py`
   - `src/adapters/{name}/mapping.py`
4. **Modifies existing files**:
   - `src/config.py` — adds env-var fields + `configured_brokers()` entry
   - `src/adapters/registry.py::load_all_adapters()` — imports + registers
   - `.env.example` — adds a new broker section with dev-portal URL
5. **Does NOT touch**:
   - `src/schemas/session.py` — the `extras: dict[str, Any]` field
     on `BrokerSession` absorbs every per-broker quirk we've seen;
     first-class schema changes are a deliberate decision, not an
     auto-generator's job
   - `frontend/` — the frontend speaks to the backend via HTTP, so
     no frontend edits are needed for a new broker
   - `tests/` beyond the automatic smoke-test coverage the
     existing `test_adapters_smoke.py` provides
6. **Prints a "next steps" block** — SDK install command, broker
   developer-app form values, IP whitelist note, and a sanity-check
   curl to hit `/brokers`.

## Scope guardrails — read before generating

- **Cash equity only.** Our codebase scopes `ProductType` to `CNC` + `MIS`
  and `Exchange` to `NSE` + `BSE`. F&O / commodities are out of scope.
  If the new broker only supports derivatives, explain this to the user
  and stop — do not expand the canonical enums silently.
- **Use the official SDK if one exists.** All 5 existing adapters wrap
  an official SDK (`kiteconnect`, `upstox-python-sdk`, `smartapi-python`,
  `fyers-apiv3`, `growwapi`). That's the established pattern. Only fall
  back to raw `httpx` calls if no SDK is available.
- **Don't copy OpenAlgo code.** OpenAlgo is AGPL-licensed; we use it
  as a reference to learn the broker's real API (endpoints, header
  formats, error shapes) but every line we write is original. If you
  catch yourself pasting from a `github.com/marketcalls/openalgo`
  fetch result, stop and rewrite.

## Step-by-step procedure

### Step 1 — Gather the spec

Ask the user (or extract from their message) the following. If any
value isn't obvious, ask before proceeding. Keep the list short.

1. **Broker name (lowercase, no spaces)** — used as the adapter folder
   name and registry key. Examples: `dhan`, `paytmmoney`, `iifl`,
   `fivepaisa`.
2. **Display name** — human-friendly. Example: `Paytm Money`.
3. **Auth kind** — one of:
   - `oauth_redirect` — user is sent to the broker's login page, broker
     redirects back with a code/token (Zerodha, Upstox, Fyers pattern).
   - `credentials_form` — user types client ID / PIN / TOTP into a form
     WE render (AngelOne pattern).
   - `api_key_only` — no user interaction, server-to-server token fetch
     using env-configured credentials (Groww pattern).
4. **Official Python SDK package name (if any)** — e.g. `dhanhq`,
   `py5paisa`. Leave blank if none; we'll use `httpx` against the
   documented REST endpoints.
5. **Developer portal URL** — e.g. `https://dhanhq.co/api-docs`. Shown
   in `.env.example` so a reviewer knows where to get credentials.

### Step 2 — Fetch reference material

In this order, fetch (via WebFetch) and summarize for Claude's own
context:

1. **Broker's official SDK docs** (primary). If a package name was
   provided:
   - Pull the SDK's `place_order` / authentication signatures.
   - Identify field names, product-type codes, exchange enum values.
2. **OpenAlgo reference** (secondary, only if the broker is supported
   there). Try:
   `https://raw.githubusercontent.com/marketcalls/openalgo/main/broker/{name}/api/auth_api.py`
   `https://raw.githubusercontent.com/marketcalls/openalgo/main/broker/{name}/api/order_api.py`
   `https://raw.githubusercontent.com/marketcalls/openalgo/main/broker/{name}/mapping/transform_data.py`
   - If they return 404, OpenAlgo doesn't support this broker — note
     that in the "next steps" output so the user knows adapter
     correctness depends on SDK docs alone.
   - If they load, skim for: endpoint URLs, header format, error
     codes, field name translations. Do NOT copy code.

### Step 3 — Generate the adapter files

Use the templates in `templates/` as starting points. The three
`adapter_*.py.template` files map to the three `auth_kind` values.
Substitute `{{BROKER_NAME}}` (lowercase), `{{BROKER_DISPLAY_NAME}}`,
`{{BROKER_CLASSNAME}}` (CamelCase, e.g. `Dhan` or `PaytmMoney`),
`{{SDK_PACKAGE}}`, `{{DEV_PORTAL_URL}}`, and any SDK-specific
method names the user needs.

**File 1:** `src/adapters/{{BROKER_NAME}}/__init__.py`
  → re-exports the adapter class.

**File 2:** `src/adapters/{{BROKER_NAME}}/adapter.py`
  → full adapter class subclassing `BrokerAdapter`, filling in:
    - The correct auth-method group for the declared `auth_kind`
    - `authorization_header`, `place_order`, `cancel_order`,
      `get_order_status`, `get_holdings`

**File 3:** `src/adapters/{{BROKER_NAME}}/mapping.py`
  → `PRODUCT_MAP`, `PRICE_TYPE_MAP`, `EXCHANGE_MAP` translating our
    canonical enums to the broker's wire values. Include any
    broker-specific helper functions (symbol builders, segment
    lookups) alongside.

### Step 4 — Wire into config + registry + .env.example

**`src/config.py`** — add to the `Settings` class fields section:
```python
{{BROKER_NAME}}_api_key: str = ""
{{BROKER_NAME}}_api_secret: str = ""
# ... any broker-specific fields like totp_secret, client_code ...
```
And add to the `configured_brokers()` method's `pairs` dict:
```python
"{{BROKER_NAME}}": (self.{{BROKER_NAME}}_api_key, self.{{BROKER_NAME}}_api_secret),
```

**`src/adapters/registry.py`** — in `load_all_adapters()`:
```python
from src.adapters.{{BROKER_NAME}} import {{BROKER_CLASSNAME}}Adapter
...
_register_once({{BROKER_CLASSNAME}}Adapter)
```

**`.env.example`** — append a new section:
```
# {{BROKER_DISPLAY_NAME}} — {{DEV_PORTAL_URL}}
{{BROKER_NAME_UPPER}}_API_KEY=
{{BROKER_NAME_UPPER}}_API_SECRET=
```

### Step 5 — Verify

Run:
```bash
uv run ruff check src tests
uv run pytest
```

Both should still pass. The existing `test_adapters_smoke.py` will
automatically include the new broker because it enumerates everything
`load_all_adapters()` registers.

### Step 6 — Report back to the user

Output a short summary like:

```
✓ Scaffolded the {{BROKER_DISPLAY_NAME}} adapter.

Files created:
  src/adapters/{{BROKER_NAME}}/__init__.py
  src/adapters/{{BROKER_NAME}}/adapter.py
  src/adapters/{{BROKER_NAME}}/mapping.py

Files updated:
  src/config.py          — added env fields
  src/adapters/registry.py — registered the adapter
  .env.example           — added credentials section

Next steps:
  1. Install the SDK:
       uv add {{SDK_PACKAGE}}
  2. Create a developer app at {{DEV_PORTAL_URL}}.
     Set the redirect URL to: http://localhost:8000/auth/{{BROKER_NAME}}/callback
  3. Whitelist your public IP in the broker's developer console
     (SEBI mandate for order placement — required for every broker
     since April 2026). Find your IP: curl -s https://api.ipify.org
  4. Copy your API key + secret into .env:
       {{BROKER_NAME_UPPER}}_API_KEY=...
       {{BROKER_NAME_UPPER}}_API_SECRET=...
  5. Restart the backend (make dev-backend or docker compose up)
     and verify the broker appears in GET /brokers with
     "configured": true.
  6. Review {{BROKER_DISPLAY_NAME}}'s error-code shapes — if they
     differ meaningfully from our existing taxonomy, add broker-
     specific patterns to classify_message() in src/adapters/errors.py.

OpenAlgo reference: {{OPENALGO_NOTE}}
```

## Things to watch for during generation

- **Auth-method mismatch.** If the user says `auth_kind=oauth_redirect`
  but you've actually generated `credential_fields()` and
  `authenticate_with_credentials()`, the registry validator will
  reject the adapter at import time with a `TypeError`. Run the
  tests after generating.
- **Missing env var propagation.** If you add `{{BROKER_NAME}}_api_key`
  to `config.py` but forget to update `configured_brokers()`, the
  broker will show up as "Not configured" in the UI even when the
  env is set. Double-check both places.
- **Classname collision.** Two brokers named similarly (e.g. `iifl`
  and `iiflcapital`) must have distinct Python class names.
  `{{BROKER_CLASSNAME}}Adapter` needs to be unique across `_ADAPTERS`.
- **BrokerSession extras.** If the broker returns anything unusual
  during auth (a feed token, a refresh token, a public token, an
  app_id, a session_id separate from access token), put it in
  `session.extras = {...}` as a named key. Never add a new field
  to `BrokerSession` in this skill — that's a schema-level decision.
- **ACTION_MAP.** The mapping.py template gives you PRODUCT_MAP,
  PRICE_TYPE_MAP, EXCHANGE_MAP. Many brokers ALSO want an
  `ACTION_MAP` — Paytm uses `B`/`S`, Fyers uses `1`/`-1`, others
  accept literal `BUY`/`SELL`. Add ACTION_MAP to mapping.py when
  the broker's wire values for side differ from our enum strings.
- **Authorization header is broker-specific.** The default template
  sets `Authorization: Bearer {access_token}`. Real brokers vary
  wildly:
    Zerodha: `Authorization: token {api_key}:{access_token}`
    Fyers:   `Authorization: {app_id}:{access_token}`
    Paytm:   `x-jwt-token: {access_token}` (not `Authorization:` at all)
    AngelOne: `Authorization: Bearer ...` PLUS `X-PrivateKey: ...`
  Check the broker's docs and override `authorization_header` to
  match. This is one of the main per-broker quirks.
- **Symbol lookup is a known gap class.** Many brokers don't accept
  plain trading symbols — they need a numeric instrument ID:
    Upstox:    instrument_key (NSE_EQ|INE002A01018)
    AngelOne:  symbol_token (numeric)
    Paytm:     security_id (numeric)
  Expect to implement a `_lookup_xxx()` method that either queries
  the broker's scrip-master CSV or uses a cached dict. Zerodha,
  Groww, and Fyers are simpler — they accept tradingsymbol +
  exchange directly. Surface this in the generated adapter as a
  `raise NotImplementedError` with a clear comment if the broker
  needs it, so the user knows to wire it up before live testing.
- **Login URL quirks.** The `oauth_redirect` template takes a
  `redirect_uri` argument, but some brokers' login URLs ignore it
  (they use the one registered in the dev console and pass it via
  API config) — Paytm's login URL is just `?apiKey={key}&state={s}`,
  no redirect_uri query param. Use `del redirect_uri` in
  build_login_url if the broker doesn't accept it in the URL.
- **Update tests that hard-code broker counts.** The existing tests
  in `tests/test_adapters_smoke.py` and `tests/test_health.py`
  used to assert on an exact set of 5 brokers. These were relaxed
  to `.issubset()` checks on the "original 5" — if you add a new
  broker and a test fails complaining about a broker count, it's
  the same class of fix: change `==` to `.issubset()`.
- **.env.example placement.** Add the new broker section at the
  BOTTOM of the existing broker block, not interleaved. Keep the
  file readable top-to-bottom (older brokers stay in the order
  they were added).

## When this skill should refuse

Stop and tell the user, don't just plow ahead, if:

- The broker only supports F&O / commodities (we're cash-equity only).
- The broker's API is paid / gated beyond a trading account (note it
  clearly; user may still want to proceed with a stub for
  demonstration, but they should know).
- The `auth_kind` doesn't actually map to one of our three kinds
  (for example: a broker requires a multi-step OTP-then-secret-key
  flow that doesn't fit `credentials_form`). In that case the skill
  should explain the mismatch and suggest either (a) collapsing the
  flow into one form, or (b) extending the `AuthKind` enum manually.
- The broker name collides with an existing adapter.

In any of those cases, explain the problem and stop. Don't generate
half-broken scaffolding.
