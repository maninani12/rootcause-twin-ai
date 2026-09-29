# RootCause Twin AI

**Persistent factory intelligence that learns from every investigation.**

A runnable manufacturing investigation demo with a Flask interface, Hindsight Cloud memory, transparent context comparison, and human-verified learning.

## Problem

Machine failures, product quality defects, and troubleshooting outcomes are often recorded separately. Teams lose the connection between operating conditions, failed fixes, verified causes, and measured outcomes. The same symptom can trigger repeated unsuccessful actions—or hide an entirely different cause.

## Solution

RootCause Twin brings the current incident and prior organizational experience into one investigation workflow. Report the defect and machine context, recall past evidence, compare conditions, investigate, and retain a human-verified resolution.

## Core Innovation

The agent remembers manufacturing context, failed actions, successful actions, confirmed root causes, and before/after outcomes. Failed corrective actions remain useful evidence instead of disappearing from the record.

## Why Hindsight?

Without Hindsight, RootCause Twin is a generic troubleshooting assistant.
With Hindsight, it learns from verified organizational experience including failed and successful corrective actions.

It becomes organization-specific over time through persistent retention and retrieval, not model retraining. Historical similarity does not establish the current root cause.

## How Hindsight Is Used

- **RETAIN:** `retain_incident(content)` sends human-verified incident outcomes to `rootcause-twin` using synchronous retention.
- **RECALL:** `recall_incidents(query)` retrieves relevant experience and original source chunks. Cards show returned evidence, never silently substituted demo data.
- **REFLECT:** Not implemented in this MVP. Guidance uses deterministic comparison; richer pattern reasoning is future work.

The integration preserves `hindsight-client==0.10.2`. The only recall extension is the supported `include_chunks=True` option. Sources are deduplicated by text. Structured source records display before extracted facts, using SDK relevance scores within each group when available. Scores are not confidence percentages.

## Known / Partial / Novel

| Classification | Transparent rule |
| --- | --- |
| KNOWN | A recalled record matches machine, defect and condition with no conflict in other supplied context. |
| PARTIAL | A recalled record matches machine or defect, but condition/context differs or is missing. |
| NOVEL | No useful recalled machine or defect overlap. |

Comparison lowercases text, tokenizes it, and checks at least 75% coverage of the supplied factor's tokens. Stable and unstable torque are explicitly treated as contradictory. The UI shows matched factors, differing/missing factors and classification reasons. These are heuristic context categories, not AI confidence or proof of causation.

## Example

- **INC-001:** A synthetic verified historical incident: unstable torque and leakage; calibration failed; worn chuck confirmed; replacement reduced defects from 4.8% to 0.2%. The existing cloud test retains this example.
- **INC-002:** Open similar demo context with a 3.9% before metric. Recall should retrieve INC-001 when it is in the bank, producing KNOWN when conditions match.
- **INC-003:** Stable torque and a new cap supplier. Relative to INC-001, this is PARTIAL and prompts cap dimension and incoming material checks. The local dataset contains its example resolution, but the report form excludes that answer. It is not automatically added to cloud memory.

Classification depends on actual bank contents. If matching supplier incidents are later retained, INC-003 may appropriately become KNOWN. No forced demo classification is applied.

## Architecture

```text
User → Flask UI → Incident Analyzer
                     ├── Hindsight RECALL → Source evidence
                     └── Context comparison
                                ↓
                      KNOWN / PARTIAL / NOVEL
                                ↓
                     Evidence-based guidance
                                ↓
                       Human verification
                                ↓
                  VERIFIED only → Hindsight RETAIN
                                ↓
                     Local resolution ledger
```

See `docs/architecture.md` for data flow, verification boundaries and storage details.

## Tech Stack

Python 3.10+, Flask 3.1.2, Jinja HTML, responsive CSS, minimal JavaScript, SQLite (standard library), python-dotenv, and Hindsight Cloud through hindsight-client 0.10.2. No external LLM is needed for guidance.

## Project Structure

```text
rootcause-twin-ai/
├── backend/
│   ├── __init__.py
│   ├── app.py
│   ├── hindsight_service.py
│   ├── incident_service.py
│   ├── store.py
│   ├── test_hindsight.py
│   ├── templates/             # dashboard, report, analysis, resolve, about
│   └── static/
│       ├── css/app.css
│       └── js/app.js
├── data/sample_incidents.json
├── docs/architecture.md
├── tests/test_app.py
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
└── README.md
```

`data/local.sqlite3` is created at runtime and ignored. `work/` is ignored development scratch space.

## Installation

Windows PowerShell, from the project folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

If `python` is unavailable, use `py` or the full path to your Python installation. Activation is not required. If your existing virtual environment is already set up, only run the install command.

Create `.env` only if it does not already exist:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Set your actual key locally, using the following names:

```dotenv
HINDSIGHT_API_KEY=your_hindsight_api_key_here
HINDSIGHT_BASE_URL=https://api.hindsight.vectorize.io
HINDSIGHT_BANK_ID=rootcause-twin
```

Use the actual bank ID if its display name differs. Existing process environment variables take precedence over `.env`. The key stays server-side.

Start the application:

```powershell
.\.venv\Scripts\python.exe run.py
```

Open **http://127.0.0.1:5000**. The server binds only to localhost, with `debug=False`.

The first dashboard request performs one real, read-only recall to verify bank access. Subsequent counters use local data. Connection badges reflect recent successful cloud operations; after five minutes they request another check. Use **Check connection** to recheck explicitly. Cloud latency can delay operations; the SDK default timeout is 300 seconds.

## Hindsight Test

This writes synthetic INC-001 experience to your configured bank:

```powershell
.\.venv\Scripts\python.exe -m backend.test_hindsight
```

Success shows `Memory stored successfully.` followed by returned memories. Repeated runs can add duplicate evidence because the existing generic retain wrapper does not assign a document ID.

## Live Demo

1. Run the Hindsight test to seed INC-001 if needed.
2. Open the dashboard and confirm CONNECTED and bank `rootcause-twin`.
3. Click **Report New Incident → Load INC-002 Demo → Analyze with RootCause Twin**.
4. Inspect **KNOWN CASE**, **HINDSIGHT MEMORY ACTIVE**, INC-001, failed calibration, worn chuck, successful replacement, and **4.8% → 0.2%**.
5. Review the guidance to inspect chuck wear and torque consistency before repeating calibration.
6. Click **Proceed to Resolution**. Enter worn capping chuck, chuck replacement, SUCCESS, 3.9%, 0.2%, and VERIFIED.
7. Click **Verify & Add to Hindsight Memory** and confirm **Retained Successfully**.
8. Click **Analyze Another Incident**, load INC-003 and analyze. Relative to unstable-torque history, inspect PARTIAL, torque differences, and supplier checks.

Demo forms are explicitly synthetic context. Resolutions from them retain a synthetic-demo origin marker. Only actual successful Hindsight operations produce success messages. No offline fallback pretends that recall worked.

## Testing

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Offline regression tests explicitly mock cloud calls; runtime application routes always call the actual service. Coverage includes pages, source evidence, KNOWN/PARTIAL/NOVEL, empty/malformed results, missing fields, sanitized network errors, verified-only retention, repeat submissions, session isolation, CSRF and HTML escaping.

## Security

- Never hardcode API keys, render them, log raw cloud errors, or commit `.env`.
- `.env`, virtual environments, runtime SQLite files and scratch files are Git-ignored. `.env.example` contains a placeholder only. Never force-add `.env`.
- Jinja autoescapes user and recalled content; forms validate required fields, length and allowed statuses, and reject control characters.
- Forms use CSRF tokens; incident pages are restricted to the originating browser session.
- No uploads, shell execution from form values, `eval`, or arbitrary code execution.
- The MVP is a local demo, not an authenticated production service. Do not expose the development server publicly.

## Operational Limits

The local ledger persists in SQLite, but the randomly generated session signing key changes on restart, so old browser-session records are no longer visible through the UI. Cloud memory remains persistent. Dashboard totals describe the three demo records plus this browser's investigations; they are not a cloud inventory.

If retention times out or fails without a definite outcome, the incident is marked UNCERTAIN and further submissions are blocked to avoid duplicates. Check the bank manually before starting another resolution. A server interruption during retention similarly leaves RETAINING for manual review. Unverified resolutions are rejected and not stored as trusted memory.

Structured fields are extracted from labeled returned source text. Missing fields are shown as missing; unstructured recalled facts remain readable. The heuristic can miss paraphrases or more complex contradictions. There is no automatic cause confirmation, authenticated verifier identity, Reflect call, or production deployment.

## Team

- Team name: [Add team name]
- Members: [Add names and roles]

## Future Scope

Larger manufacturing data integrations, production system connectors, asset-specific memory banks, richer Reflect-based pattern analysis, and maintenance/quality system integrations.

SDK references: https://pypi.org/project/hindsight-client/0.10.2/ and https://hindsight.vectorize.io/sdks/python.
