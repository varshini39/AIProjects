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
└── n8n/
    └── FinEdge_LinkedIn_Automation.json   # Exported n8n workflow
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

Before you start: n8n must be running (`n8n start`, section 4.1) and the
FastAPI microservice must already be up on `http://localhost:8000`
(section 4.2) — the third node below calls it directly.

**Import the workflow**
1. Open the n8n editor at `http://localhost:5678`.
2. Top-right menu (**⋯**) → **Import from File** (or drag-and-drop the file
   onto the canvas).
3. Select `n8n/FinEdge_LinkedIn_Automation.json`. The full workflow appears
   on the canvas: `Schedule Trigger → Brand Config → AutoGen Microservice →
   Compose Final → Approval Gate → Dry Run Check → ...`.

**Run each node in isolation** ("Execute Node" lets you test one step at a
time without triggering the whole workflow — useful for catching config
mistakes early):

1. **Brand Config** (a `Set` node — holds the brand/context payload)
   - Single-click the node to select it (don't double-click yet).
   - Click the **Execute step** button that appears on the node itself
     (▶ icon, bottom-center of the node), or double-click the node to open
     its panel and click **Execute step** there.
   - A green checkmark appears on the node when it succeeds. Click the
     node again (or look at the **Output** panel on the right) to inspect
     the JSON — confirm it contains your `brand` and `context` fields
     (name, industry, voice, topic, audience, min_confidence, etc.).

2. **AutoGen Microservice** (an `HTTP Request` node — calls the FastAPI
   service)
   - Double-click to open it first and check the **URL** field points to
     `http://localhost:8000/linkedin` (edit it if your service runs on a
     different host/port), and that **Method** is `POST` with the JSON
     body mapped from the previous node's output.
   - Click **Execute step** in the node panel (or the ▶ icon on the
     canvas). This sends a real HTTP request — your FastAPI terminal
     should log the incoming request.
   - Check the **Output** panel: you should see `ideas`, `draft`,
     `hashtags`, `confidence_score`, `meets_threshold`, `reviewer_notes`,
     `agent_trace` — the same shape you saw from the curl test in 5.1.
   - If it fails instead: see the troubleshooting table in section 6
     (most likely cause is the microservice isn't running or the port is
     wrong).

3. **Compose Final** (a `Set` node — merges draft + hashtags into one
   postable string)
   - Double-click to open, click **Execute step**.
   - In the **Output** panel, confirm a `final_text` field exists and
     that it reads as `draft` followed by the hashtags, e.g. ends with
     `#Fintech #LinkedInGrowth ...`.

4. **Approval Gate** (an `If` node — routes on `confidence_score` vs.
   `min_confidence`)
   - Double-click to open, click **Execute step**.
   - n8n highlights which output branch fired: the top/green connector is
     the "pass" (auto-approve) path, the bottom is "fail" (needs rework).
   - To see both branches: go back to **Brand Config**, edit
     `min_confidence` to a value just above the microservice's returned
     `confidence_score` (e.g. `0.95`), re-run steps 1–4, and confirm the
     **fail** branch now highlights instead. Set it back afterward.

If any node's Execute step fails, n8n shows a red X on the node and an
error panel with the message — read that first before checking section 6.

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
| n8n `AutoGen Microservice` fails with `ECONNREFUSED ::1:8000` even though `curl http://localhost:8000/health` works | Node.js resolves `localhost` to the IPv6 loopback `::1` first, but `uvicorn` only binds IPv4 (`0.0.0.0`); `curl` on macOS tries IPv4 first so it doesn't hit this | Use `http://127.0.0.1:8000/linkedin` instead of `http://localhost:8000/linkedin` in the HTTP Request node's URL field — forces IPv4 and skips the broken IPv6 lookup |
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
