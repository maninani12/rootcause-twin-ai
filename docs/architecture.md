# Architecture

## 1. System overview

RootCause Twin is a localhost Flask application. Hindsight is the persistent organizational memory; SQLite is a local investigation ledger. The JSON file contains clearly labeled synthetic examples and is not automatically uploaded.

```text
Browser (Jinja + CSS + small JS)
     │ validated forms + CSRF
     ▼
Flask routes ──────────────── Local SQLite ledger
     │                            │
     ▼                            └─ session-owned records + retention state
Incident service
     ├─ query builder
     ├─ source normalization
     ├─ deterministic comparison
     └─ evidence-based guidance
     │
     ▼
Existing hindsight_service.py
     ├─ recall_incidents(query) ─────── Hindsight Cloud / rootcause-twin
     └─ retain_incident(content) ────── VERIFIED outcomes only
```

## 2. Data flow

GET `/` derives counters from the three sample records plus the browser session's ledger. The first dashboard view performs a read-only recall check; subsequent counters do not call the cloud. Status is based on actual operations and becomes stale after five minutes.

GET `/incident/new` renders the form. Demo buttons load current incident context only. POST `/incident/analyze` validates input, queries Hindsight, normalizes evidence and persists the analysis locally. GET `/incident/<id>` displays the analysis and evidence. Failed or malformed recall returns a friendly error and never produces a synthetic success.

## 3. Hindsight retain flow

GET/POST `/incident/<id>/resolve` shows the current incident and requires a cause, action, result, before/after metric and verification status. UNVERIFIED submissions are rejected. VERIFIED includes verified unsuccessful or partial actions; verification is not synonymous with success.

An atomic SQLite transition OPEN → RETAINING prevents duplicate submissions. Rich labeled natural language preserves context, previous attempted action, current corrective action and outcome. The existing synchronous retain function performs the write. API success changes the local state to RETAINED. A failed/ambiguous request changes it to UNCERTAIN; there is no automatic retry. A crash may leave RETAINING. Both states require manual cloud review before a new submission. The success screen renders only for RETAINED.

## 4. Hindsight recall flow

Queries include machine, product, defect, machine condition and recent changes. The SDK call requests `include_chunks=True`, supported in 0.10.2. The normalizer accepts the SDK model or a dictionary, validates response shape, and uses only source text actually returned. Exact source text is deduplicated. Structured source records appear first, ordered by SDK scores when available; extracted facts follow. No score is called confidence.

A label parser extracts fields from individual source records. Missing verification remains unverified/not stated. Local JSON never fills holes in recalled memories. Unstructured facts are shown as raw evidence. No fact fragments from unrelated sources are merged into a fabricated incident.

## 5. Known / Partial / Novel logic

Each recalled record is compared independently. The rule checks machine, defect, condition, product and recent change using lower-case token overlap (75% coverage). A stable-versus-unstable torque conflict explicitly overrides lexical similarity.

- KNOWN: a record matches machine, defect and condition without a supplied context conflict.
- PARTIAL: machine or defect matches but other context differs or is missing.
- NOVEL: no useful machine or defect overlap.

The best matching record supplies displayed matched/different factors. Rules are deterministic, intentionally conservative, and cannot prove causation. Guidance lists documented failed actions, successes, root causes and metrics. For stable torque with a supplier change, it recommends material checks without asserting the supplier is the current cause.

## 6. Human verification boundary

A person explicitly selects VERIFIED. Only then can the application invoke retain. This local MVP does not authenticate the verifier or independently prove the measurements. Demo outcomes are marked synthetic in retained text. Reflect is not called. Current incidents never inherit a historical confirmed root cause automatically.

## 7. Security and storage

Credentials load server-side from the project `.env` or environment; never from browser input. Git ignores `.env`, runtime databases, environments and scratch work. Raw SDK exceptions are not rendered or logged by application handlers. Jinja autoescaping, length/status validation, single-line fields, CSRF, session ownership, security response headers and localhost binding protect the demo boundary.

SQLite connections commit or roll back and always close, including on Windows. SQL uses parameters. No form triggers shell execution or dynamic code. A random per-process signing key means browser-session access resets when the server restarts. The ledger and cloud memories remain stored; production identity, recovery controls and audit retention are future work.
