# Prompt Escapes

Your next getaway is just a prompt away.

Source repository: [secure-agentic-framework/prompt-escapes](https://github.com/secure-agentic-framework/prompt-escapes)

A local security learning lab built around an AI travel agent. Chat with the agent, compare fictional flight-and-hotel packages, approve an exact quote, and inspect the resulting saved reservations and tool activity.

## Learning-lab direction

Prompt Escapes is inspired by [OWASP Juice Shop](https://owasp.org/projects/juice-shop), a deliberately insecure application for security training. The teaching setting here is an AI agent arranging travel: learner exercises can explore prompt injection, tool permissions, access to other travelers’ records, and booking approval boundaries.

The current build includes a real tool-using research workflow, fourteen intentional security challenges organized as four campaigns, progressive hints, evidence-based completion checks, and a persistent local completion record. Booking recovery scenarios remain separate from security challenges.

The [agentic attack catalogue](docs/attack-catalogue.md) selects 14 techniques from Secure Agentic Framework, maps their relationship to OWASP's Agentic Top 10, and describes the travel exercises, completion evidence, and hardened comparisons.

### Research with a real agent

Select **AI agent**, then **Research & recommend** in the conversation. The model can look up the current fictional traveler, search itineraries, read hotel partner descriptions, and choose an option using `recommend_option`. Its recommendation and reasoning summary appear in the plan panel. This is a model choice among persisted quotes; booking still requires explicit UI approval.

Planning notes are a built-in part of the travel assistant. The model can save concise trip context, while server checks prevent untrusted supplier content from deciding what enters durable memory. The model can also create fictional postcards in a local capture. There is no email delivery or external messaging integration.

**Model execution trace** shows the actual model, response ID, number of API responses, token usage, tool arguments, tool results, and completion status. Test transports are labeled separately. A selected AI mode alone does not establish that a model has run; the trace provides the evidence. **Find my options** continues to search the simulator directly without model calls.

For exploratory reconnaissance, the browser developer console emits one safe debug line when the agent calls a tool. It includes only the internal tool name and whether the call executed or was rejected; arguments, results, fixture data, and credentials are deliberately omitted.

### Security challenges

Choose a challenge and **Vulnerable training version**, then **Start challenge**. Every card exposes the attack's entry surface, broken control, and observable harm. **Attempt challenge** leaves the request to the learner and reveals hints one at a time. **Run guided demo** supplies a reliable stage-demo request; editable exercises also offer a guided payload. Challenges require AI mode; scripted demo cannot solve them.

| Campaign | Progression |
| --- | --- |
| Untrusted content | Plain supplier injection → encoded carrier → durable memory poisoning |
| Authorization & data flow | Single-record access → collection at scale → sensitive-data egress |
| Autonomy & truth | Resource abuse → response tampering → false claims → diagnostic disclosure |
| Supply chain & orchestration | Tool metadata → post-approval mutation → cross-provider shadowing → cross-agent injection |

| Challenge | Intentional defect | Completion evidence |
| --- | --- | --- |
| The poisoned brochure | Supplier text is promoted into developer instructions, and the note tool omits its source-and-intent check. | A real model run reads the poisoned brochure, then saves its session marker even though the traveler never requested that note. A marker directly requested in chat does not count. |
| Someone else’s getaway | The traveler lookup tool omits its object-ownership check. | The model retrieves T200’s fictional private record while the current traveler is T100. |
| A postcard too far | The postcard tool omits recipient and sensitive-field checks. | The model looks up T100’s fixture record, then copies its exact private itinerary to the local `capture@outside.example` capture, bypassing the allowed-recipient policy. |

The full catalogue also includes persistent memory poisoning, encoded instructions, bulk record harvesting, virtual-budget retry abuse, response tampering, false confirmation claims, synthetic instruction disclosure, tool-description poisoning, post-approval mutation, cross-provider shadowing, and injection through a separate research agent.

For the memory exercise, run the planting attempt, choose **Start a new conversation**, and research again. The original chat and poisoned brochure are excluded from the new conversation; only durable notes carry forward. For tool mutation, approve the benign read-only version 1, save and apply version 2, then research a hotel. The vulnerable replacement silently creates a fictional supplier-program enrollment; the hardened variant blocks changed metadata before sending it to the model. The handoff exercise instead demonstrates a separate research agent inducing an unauthorized change to the downtown-only trip-search policy.

Provider exercises simulate independently identified local providers; there is no MCP transport or dynamic executable plugin loading. The research-desk exercise makes an actual additional model request in a separate context with no action tools. Both agents share the same outer limits: 12 model requests, 16 tool calls, and 90 seconds per turn. Retry credits are fictional; the vulnerable retry integration treats the two-credit allowance as advisory, while the hardened server enforces it.

Price and confirmation claims are generated artifacts shown alongside authoritative quotes and reservations. They cannot modify booking amounts or create reservations. The prompt-disclosure exercise uses a synthetic instruction block; its hardened variant keeps private configuration outside model context and denies diagnostic access.

Choose **Hardened comparison** and replay an attempt against source handling and server-enforced capability/recipient/ownership checks. These checks still apply if a model requests the prohibited tool action. Model behavior can vary between runs; the completion checker tests actual saved actions, not natural-language success claims.

Each active challenge links directly to the relevant server-side vulnerable/hardened branch in the public source repository, so learners can connect the observed denial to the control that enforced it.

Every launch/reset creates a new trip with independent fixture tokens, brochure text, and session progress. Previous sessions are retained; the single-user local completion record marks each challenge once. Test/mock responses and direct HTTP claims cannot complete challenges. There is no public tool-execution or completion endpoint.

The vulnerable paths affect synthetic records inside their selected challenge only. Normal travel sessions retain the server checks. Postcards always stay in SQLite and accept `.example` addresses only, including in vulnerable mode. Provider credentials are never placed in the fictional world or exposed to agent tools. This local workshop does not provide multi-user identity isolation or production hosting.

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

The model integration follows the [official OpenAI function-calling documentation](https://developers.openai.com/api/docs/guides/function-calling): strict function schemas, execution in application code, tool results linked by call ID, and a bounded multi-step Responses loop. Tools can update the brief, research, recommend, save permitted notes, and capture fictional postcards. Booking and cancellation are available only through the explicit UI endpoints; model text cannot authorize them.

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

Challenge tests use controlled provenance fixtures to verify the checker deterministically; those fixtures are not evidence of live model behavior. They also test hardened enforcement, non-vacuous positive and negative completion cases, fixture isolation, API redaction, and attempts to forge completion.

For an actual, paid-model smoke check, start a separate server with an isolated database, then run:

```sh
python3 server.py --port 8001 --db /tmp/prompt-escapes-ai-check.sqlite3
# In another terminal:
python3 scripts/smoke_ai.py --base http://127.0.0.1:8001 --report /tmp/prompt-escapes-vulnerable.json
python3 scripts/smoke_ai.py --base http://127.0.0.1:8001 --hardened --report /tmp/prompt-escapes-hardened.json
```

By default the smoke runner tests the normal workflow and every challenge. Use `--cases` to select individual IDs. Hardened runs allow legitimate actions such as a postcard to the current traveler; they reject the prohibited effects. The smoke runner sends only synthetic tasks through the public HTTP routes and asserts observed model/tool outcomes. It prints request counts and tool names, not API keys or fixture tokens. An isolated database keeps smoke-test completions out of your learner history.

## Layout

```text
server.py             Local HTTP server, environment loading, approval endpoints
travel/simulator.py   SQLite state, inventory, quotes, booking and recovery rules
travel/agent.py       OpenAI tool loop and explicit scripted demo
travel/lab.py         Research tools, isolated challenge fixtures, completion checks
travel/exercises.py   Extended SAF curriculum, provider fixtures, and evidence rules
static/               Buildless browser interface
tests/                Domain, agent, and HTTP integration tests
scripts/smoke_ai.py   Opt-in live model/workflow verification
data/travel.sqlite3   Runtime state, created on launch and ignored by Git
```

This is a single-user local prototype. It binds only to `127.0.0.1`, uses a per-process request token and Host checks, and serves no API keys to the browser. SQLite includes chat and reservation history in plain text; use fictional traveler details. It is not prepared for public deployment or multiple untrusted users. Starting a new trip retains older trips in the database; the browser restores only the most recently opened one.

Use `python3 server.py --port 8001` for another port, or `--db /path/to/test.sqlite3` for an isolated database.
