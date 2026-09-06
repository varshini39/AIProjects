# Reflection — Design Decisions, Challenges, and Trade-offs

## Design decisions

**Splitting the pipeline into four discrete agents (Ideation, Drafting,
Hashtag, Reviewer) instead of one large prompt.** A single "write me a
LinkedIn post" prompt is faster to build but harder to control and debug.
Separating concerns mirrors the AutoGen/AG2 `GroupChat` pattern from the
course labs and means each stage can be individually tested, logged, and
swapped — for example, the Reviewer agent can be tightened for compliance
without touching how ideas are generated.

**A mock-mode toggle (`USE_MOCK`) instead of requiring a live LLM.**
Grading, CI, and n8n's "Execute Node" testing all need fast, free,
deterministic responses. Building an offline mock implementation that
satisfies the exact same Pydantic response schema as the real AutoGen
agents meant the rest of the system (n8n workflow, approval gate,
logging) could be fully built and tested before ever spending an API
call — and the switch to real agents is a one-line env var change.

**Keeping Slack/LinkedIn/scheduling entirely out of the microservice.**
The FastAPI service only knows about brand + context in, structured
content out. All routing logic — dry-run vs. live, confidence
thresholds, Slack vs. LinkedIn — lives in n8n. This keeps the
microservice reusable (it could feed a different orchestrator later) and
keeps the approval/compliance logic visible and editable by non-engineers
in the n8n canvas, which matters for a fintech's governance requirements.

**Two-stage IF gating (Approval Gate → Dry Run Check)** rather than one
complex condition. Confidence thresholding and dry-run routing are
different concerns — separating them makes the workflow easier to read
and means a reviewer can reason about "did this pass quality?" and
"where does it go?" independently.

## Challenges

- **Getting the Reviewer agent to return structured JSON reliably.** LLMs
  frequently wrap JSON in prose or markdown fences. Solved with a
  defensive parse (slice between the first `{` and last `}`) and a safe
  fallback score, logged as a warning rather than a hard failure — so a
  malformed reviewer response degrades gracefully instead of breaking the
  whole run.
- **Deciding where "confidence" should live.** Initially considered
  computing confidence in n8n from raw fields (length, keyword presence),
  but that duplicated logic across two systems. Moved all scoring into
  the Reviewer agent so there's a single source of truth, and n8n only
  *compares* the score against a threshold.
- **Balancing automation with oversight.** It was tempting to auto-post
  anything above a modest confidence score, but for a regulated fintech
  brand, a mis-worded post is a real compliance risk. Defaulting
  `dry_run: true` and requiring an explicit flip to go live, plus routing
  low-confidence drafts to a *different* Slack channel with reviewer
  notes attached, keeps a human in the loop by default rather than by
  exception.

## Trade-offs

- **Sequential agent calls instead of a true concurrent multi-agent
  debate.** A richer AutoGen `GroupChat` where agents critique each
  other's output in multiple turns would likely produce better drafts,
  but at 3–4x the latency and API cost for a synchronous HTTP endpoint.
  For a scheduled, non-interactive workflow, sequential single-turn calls
  were judged the better fit — this could be revisited if draft quality
  proves insufficient.
- **Google Sheets over a proper database for logging.** Faster to wire
  up in n8n and immediately readable by non-technical stakeholders tuning
  the threshold, at the cost of not scaling well past a few thousand
  rows. Swapping the `Log Run` node for a Postgres/Airtable node is a
  drop-in change if volume grows.
- **Banned-word matching is a simple substring check**, not a full
  compliance/toxicity classifier. It catches the obvious cases cheaply
  and transparently, but a real fintech deployment would likely want a
  dedicated compliance-review step (possibly its own agent) before
  anything reaches the live LinkedIn branch.
