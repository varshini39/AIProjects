# FinEdge Mumbai — AI-Powered LinkedIn Content Automation
### AutoGen-style microservice + n8n orchestration (Course-End Project)

## 1. Problem recap

FinEdge Mumbai's content team spends 15+ hours/week hand-drafting LinkedIn
posts, posts inconsistently (engagement down 45%), and misses trending
topics. This project automates ideation → drafting → hashtags → review
scoring behind a human **approval gate**, so the team keeps oversight
without doing the manual work.

## 2. Architecture

```
                 ┌─────────────────────┐
   n8n Schedule  │   Brand Config       │   HTTP POST /linkedin
   Trigger  ───▶ │   (Set node)         │ ───────────────────────┐
                 └─────────────────────┘                         │
                                                                  ▼
                                              ┌───────────────────────────────┐
                                              │  AutoGen-style FastAPI         │
                                              │  microservice (main.py)        │
                                              │                                 │
                                              │  IdeationAgent  → 5 post angles │
                                              │  DraftingAgent  → draft post    │
                                              │  HashtagAgent   → hashtags      │
                                              │  ReviewerAgent  → confidence    │
                                              └───────────────┬────────────────┘
                                                               │ JSON
                                                               ▼
                 ┌─────────────────────┐   ┌─────────────────────────┐
                 │   Compose Final      │──▶│   Approval Gate (IF)     │
                 │   (Set node)         │   │  confidence ≥ threshold? │
                 └─────────────────────┘   └───────────┬─────────────┘
                                             pass │            │ fail
                                                  ▼            ▼
                                     ┌───────────────────┐  Slack:
                                     │  Dry Run Check(IF) │  needs rework
                                     └──────┬──────┬──────┘
                                    dry_run │      │ live
                                        Slack     LinkedIn
                                        review    publish
                                            │         │
                                            └────┬────┘
                                                 ▼
                                     Log Run (Google Sheets)
                                                 │
                                     (any node failure) ──▶ Slack error alert
```

**Design principle:** the microservice is a stateless, single-purpose API
(brand + context in → structured content out). n8n owns *orchestration,
routing, human-in-the-loop approval, and logging* — nothing about Slack,
LinkedIn, or scheduling lives inside the microservice. This keeps the two
systems independently testable and replaceable.

## 3. Repository contents

```
linkedin_automation/
├── main.py                 # FastAPI microservice (/linkedin, /health)
├── .env.example             # Config template (copy to .env)
├── requirements.txt
├── sample_request.json      # Sample payload for curl testing
├── runs.log.jsonl            # Created at runtime — append-only run log
├── n8n/
│   └── FinEdge_LinkedIn_Automation.json   # Exported n8n workflow
└── docs/
    └── reflection.md         # Design decisions, challenges, trade-offs
```

## 4. Environment setup

### 4.1 Node.js + n8n

Install Node.js 20+ for your OS, then install n8n via npm (works the same
on Linux, macOS, and Windows):

```bash
npm install -g n8n
n8n start   # serves the editor at http://localhost:5678
```

If you don't already have Node.js:

- **Ubuntu/Debian:**
  ```bash
  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
  sudo apt-get install -y nodejs
  ```
- **macOS:** `brew install node@20`
- **Windows:** install from [nodejs.org](https://nodejs.org) or
  `winget install OpenJS.NodeJS.LTS`

### 4.2 Python + FastAPI microservice
```bash
cd linkedin_automation
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env       # edit as needed (USE_MOCK=true is fine to start)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

`USE_MOCK=true` (the default) runs fully offline deterministic agents —
no OpenAI key required. This is intentional: it lets you test the whole
pipeline and the n8n workflow without incurring API cost, then flip
`USE_MOCK=false` once you're ready to use real AG2/AutoGen agents.

## 5. Testing each component individually

### 5.1 Microservice — curl
```bash
curl -s http://localhost:8000/health

curl -s -X POST http://localhost:8000/linkedin \
  -H "Content-Type: application/json" \
  -d @sample_request.json | python3 -m json.tool
```
Expected: JSON with `ideas`, `draft`, `hashtags`, `confidence_score`,
`meets_threshold`, `reviewer_notes`, `agent_trace`.

Verify the traceability log:
```bash
tail -n 5 runs.log.jsonl
```

Verify guardrails (banned-word detection should drop confidence):
```bash
curl -s -X POST http://localhost:8000/linkedin \
  -H "Content-Type: application/json" \
  -d '{"brand":{"name":"FinEdge Mumbai","banned_words":["guaranteed"]},
       "context":{"topic":"guaranteed high yield savings account"},
       "dry_run": false, "min_confidence": 0.9}' | python3 -m json.tool
```

### 5.2 n8n — Execute Node
1. Import `n8n/FinEdge_LinkedIn_Automation.json` (Workflows → Import from File).
2. Open **Brand Config**, click **Execute Node** — confirm it outputs the
   brand/context object.
3. Open **AutoGen Microservice**, click **Execute Node** — confirm it
   calls `http://localhost:8000/linkedin` and returns the microservice's
   JSON (edit the URL if the service is on a different host/port).
4. Open **Compose Final**, **Execute Node** — confirm `final_text` combines
   `draft` + `hashtags`.
5. Open **Approval Gate**, **Execute Node** — toggle `min_confidence` in
   Brand Config to see both branches fire.

### 5.3 Full workflow
1. Configure credentials: Slack (incoming webhook or OAuth) and, when
   ready to go live, LinkedIn OAuth2 (`LinkedIn - Publish` node) with your
   organization's URN.
2. Run the workflow manually (▶ button) with `dry_run: true` in
   **Brand Config** — confirm the draft lands in the `#linkedin-drafts`
   Slack channel.
3. Lower `min_confidence` temporarily to force the "needs rework" branch
   and confirm the Slack alert fires with reviewer notes attached.
4. Check the **Log Run (Google Sheets)** node appended a row with
   `run_id`, `confidence_score`, `meets_threshold`, and `final_text`.
5. Re-enable the **Schedule Trigger** for the weekday 09:00 cadence once
   satisfied.

## 6. Error handling & resolutions encountered

| Symptom | Root cause | Fix |
|---|---|---|
| n8n `AutoGen Microservice` node times out | FastAPI server not running / wrong port | Confirm `uvicorn` is up on the URL configured in the HTTP Request node; increase `options.timeout` if agent calls are slow |
| `/linkedin` returns `422 Unprocessable Entity` | Request body missing required `context.topic` field | Fixed by validating the Pydantic schema in Brand Config before sending |
| Reviewer confidence always `0.7` in AutoGen mode | LLM occasionally returns prose instead of the requested JSON | `ReviewerAgent` output is now defensively parsed (`json.loads` between first `{` and last `}`) with a safe fallback score + logged warning |
| Slack node fails silently | Missing/expired webhook credential | Added a dedicated **Slack - Error Alert** node wired to the workflow's error output so failures are never silent |
| Draft posts run over LinkedIn's ideal length | No length guardrail | `context.max_length` is enforced in both mock and AutoGen drafting agents, and `ReviewerAgent` penalizes drafts outside 300–1200 chars |

## 7. Tuning the confidence threshold

`min_confidence` (default `0.75`, set in `.env` and mirrored in Brand
Config) controls how much is auto-approved vs. sent back for rework.
Start conservative (0.8–0.9) while you calibrate the Reviewer agent
against real posting outcomes logged in the **Runs** sheet, then relax it
as trust in the pipeline grows.

## 8. Submission checklist

- [x] Microservice code — `main.py`, `.env.example`
- [x] Exported n8n workflow JSON — `n8n/FinEdge_LinkedIn_Automation.json`
- [ ] Screenshots of successful runs — capture from your running n8n
      instance and FastAPI docs (`/docs`) and add to `docs/screenshots/`
- [x] Reflection on design decisions, challenges, and trade-offs —
      `docs/reflection.md`
