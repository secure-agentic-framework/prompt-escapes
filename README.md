# Wayfarer

A local travel-agent playground: chat with an agent, compare fictional flight-and-hotel packages, approve an exact quote, and inspect the resulting saved reservations and tool activity.

## Run

Requires Python 3.9 or later. No Python dependencies, package installation, or frontend build is needed.

```sh
python3 server.py
```

Open **http://127.0.0.1:8000**. Choose **Find my options**, review an itinerary, and select **Approve & book**. The confirmation dialog binds approval to that option and total. Refreshing the page restores the last trip from SQLite.

### AI mode

Start the server from a terminal where `OPENAI_API_KEY` is exported. It reads the environment of the server process, not other terminals or the browser. Restart the server after changing the key.

You may alternatively copy `.env.example` to `.env` and set the key there. `.env` is ignored by Git. Never paste a key into chat or put it in frontend code.

`OPENAI_MODEL` selects the model (default `gpt-6.1-sol`); choose a tool-capable Responses API model available to your account. Model calls use your API account and may incur charges. Only messages and the current fictional trip state are sent to OpenAI. The app sets `store: false`; this does not override provider retention policies.

Without a key, **Scripted demo** mode works offline. It recognizes supported city names/airport codes, `$budgets`, numeric nights, and pairs of ISO dates. It is a keyword script, not an AI model. It never silently substitutes for a failed AI request. The structured brief works in either mode.

The model integration follows the [official OpenAI function-calling documentation](https://developers.openai.com/api/docs/guides/function-calling): strict function schemas, execution in application code, tool results linked by call ID, and a bounded multi-step Responses loop. Tools can update the brief, search, and read state. Booking and cancellation are available only through the explicit UI endpoints; model text cannot authorize them.

## Simulation scope

- Supported airports: SFO, ORD, JFK, SEA, BOS, LAX, in either direction.
- Round-trip flights, one shared hotel room, 1–4 travelers, 1–30 nights, USD only.
- Nonstop and downtown switches are hard requirements. An impossible budget yields no options.
- Flight fares are per traveler; hotel rates are per room/night. Integer-cent totals include fictional 8% flight and 14% hotel taxes. Displayed schedules and ratings are illustrative, not real travel information.
- Prices, inventory, carriers, hotels, confirmations, payments, and refunds are all fictional. There are no real supplier integrations or payment operations.
- The prefilled trip brief is an example, not inferred traveler preferences. AI mode can clarify or update it; the user reviews dates and totals before approving.

### Recovery scenarios

Select a **New trip scenario**, then **New trip**. The selected failure triggers once, on the trip’s first approval attempt.

| Scenario | Observable outcome |
| --- | --- |
| Smooth sailing | A flight and hotel confirmation are persisted. |
| Price changes | Quotes increase before booking; nothing is reserved. The new total requires new approval and must still meet the budget. |
| Flight sells out | All quotes for that flight become unavailable. Search again to exclude it. |
| Hotel fails | The flight remains confirmed. Retry the same option to reserve only the hotel, or explicitly cancel the flight. |
| Flight times out | A fictional post-commit provider timeout is reconciled against the ledger. The saved confirmation is reused and the hotel completes. |

Retries are idempotent per quote and reservation kind. Cancelling part of a trip leaves other reservations active and invalidates that itinerary’s booking retry; cancel remaining reservations before searching a replacement. Cancellation is a full simulated refund, with history retained. Active reservations prevent changes to the trip brief or switching itineraries.

These failure scenarios are deterministic simulator events, not actual network outages. The UI’s activity log shows operations and recovery events, not private model reasoning.

## Verify

```sh
python3 -m unittest discover -s tests -v
node --check static/app.js
```

The suite exercises constraints and totals, SQLite persistence, concurrent duplicate approvals, stale consent, every recovery scenario, cancellation, a mocked multi-step model exchange, unauthorized model tools, iteration limits, and real local HTTP requests. Model-contract tests use an injected fake transport and make no paid API calls.

## Layout

```text
server.py             Local HTTP server, environment loading, approval endpoints
travel/simulator.py   SQLite state, inventory, quotes, booking and recovery rules
travel/agent.py       OpenAI tool loop and explicit scripted demo
static/               Buildless browser interface
tests/                Domain, agent, and HTTP integration tests
data/travel.sqlite3   Runtime state, created on launch and ignored by Git
```

This is a single-user local prototype. It binds only to `127.0.0.1`, uses a per-process request token and Host checks, and serves no API keys to the browser. SQLite includes chat and reservation history in plain text; use fictional traveler details. It is not prepared for public deployment or multiple untrusted users. Starting a new trip retains older trips in the database; the browser restores only the most recently opened one.

Use `python3 server.py --port 8001` for another port, or `--db /path/to/test.sqlite3` for an isolated database.
