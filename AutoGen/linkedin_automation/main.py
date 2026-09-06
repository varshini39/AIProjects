"""
FinEdge Mumbai — AutoGen-style LinkedIn Content Microservice
==============================================================

Exposes POST /linkedin, which accepts brand configuration + content context
and returns a structured JSON payload produced by a small multi-agent
pipeline (Ideation -> Drafting -> Hashtag -> Review/Scoring), mirroring the
AutoGen / AG2 group-chat pattern used in the course labs (see
AutoGen2003.ipynb: AssistantAgent + GroupChat + GroupChatManager).

Two execution modes, controlled by env var USE_MOCK:
  - USE_MOCK=true   -> deterministic, offline "mock" agents (no API key
                        needed). Great for grading / curl testing / CI.
  - USE_MOCK=false  -> real AG2 (autogen) AssistantAgents backed by an
                        OpenAI-compatible model, run as a lightweight
                        internal GroupChat.

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload

Test:
    curl -X POST http://localhost:8000/linkedin \
      -H "Content-Type: application/json" \
      -d @sample_request.json
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------

# Load only this project's own .env — an unqualified load_dotenv() walks up
# parent directories and would pick up an unrelated .env elsewhere in the repo.
load_dotenv(Path(__file__).resolve().parent / ".env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o-mini")
USE_MOCK = os.getenv("USE_MOCK", "true").lower() == "true"
LOG_FILE = Path(os.getenv("LOG_FILE", "runs.log.jsonl"))
MIN_CONFIDENCE_DEFAULT = float(os.getenv("MIN_CONFIDENCE", "0.75"))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("linkedin-microservice")

app = FastAPI(
    title="AutoGen-style LinkedIn Content Microservice",
    description="Multi-agent ideation, drafting, hashtag generation and "
                "review scoring for FinEdge Mumbai's LinkedIn automation.",
    version="1.0.0",
)


# --------------------------------------------------------------------------
# Request / response schemas
# --------------------------------------------------------------------------

class BrandConfig(BaseModel):
    name: str = Field(..., examples=["FinEdge Mumbai"])
    industry: str = Field(default="Fintech", examples=["Fintech"])
    voice: str = Field(
        default="authoritative, data-driven, approachable",
        description="Comma-separated tone/voice descriptors",
    )
    values: List[str] = Field(
        default_factory=lambda: ["trust", "innovation", "transparency"]
    )
    banned_words: List[str] = Field(default_factory=list)


class ContentContext(BaseModel):
    topic: str = Field(..., examples=["RBI's new digital lending guidelines"])
    audience: str = Field(default="fintech professionals and SME founders")
    goal: str = Field(
        default="thought leadership",
        description="e.g. thought leadership, product launch, hiring, event",
    )
    cta: Optional[str] = Field(
        default=None, description="Optional call-to-action to include"
    )
    max_length: int = Field(default=900, ge=100, le=3000)


class LinkedInRequest(BaseModel):
    brand: BrandConfig
    context: ContentContext
    dry_run: bool = Field(
        default=True, description="If true, downstream workflow should route to Slack"
    )
    min_confidence: float = Field(default=MIN_CONFIDENCE_DEFAULT, ge=0, le=1)

    @field_validator("min_confidence")
    @classmethod
    def clamp_confidence(cls, v):
        return max(0.0, min(1.0, v))


class LinkedInResponse(BaseModel):
    run_id: str
    generated_at: str
    ideas: List[str]
    draft: str
    hashtags: List[str]
    confidence_score: float
    meets_threshold: bool
    reviewer_notes: str
    agent_trace: List[str]
    mode: str


# --------------------------------------------------------------------------
# Agent layer
# --------------------------------------------------------------------------
# The pipeline is intentionally split into four discrete "agents" so it can
# be swapped between the offline mock implementation and a real AG2 /
# AutoGen GroupChat without changing the FastAPI contract.

class MockAgents:
    """Deterministic, offline stand-ins for the four AutoGen agents.

    Used when USE_MOCK=true (default) so the microservice is fully
    testable with `curl` and inside n8n's "Execute Node" without needing
    an OpenAI key or incurring API cost — useful for grading and CI.
    """

    def ideate(self, brand: BrandConfig, ctx: ContentContext) -> List[str]:
        angles = [
            f"A contrarian take on {ctx.topic} and what it means for {ctx.audience}.",
            f"3 data points {brand.name} customers should know about {ctx.topic}.",
            f"A behind-the-scenes look at how {brand.name} is responding to {ctx.topic}.",
            f"A myth-busting post correcting common misconceptions about {ctx.topic}.",
            f"A short story / customer anecdote illustrating the impact of {ctx.topic}.",
        ]
        return angles[:5]

    def draft(self, brand: BrandConfig, ctx: ContentContext, idea: str) -> str:
        cta_line = f"\n\n{ctx.cta}" if ctx.cta else "\n\nWhat's your take? Drop a comment below."
        body = (
            f"{ctx.topic} is reshaping how {ctx.audience} think about growth.\n\n"
            f"At {brand.name}, we believe {brand.values[0] if brand.values else 'trust'} "
            f"and {brand.values[1] if len(brand.values) > 1 else 'clarity'} matter more than ever "
            f"when the rules of the game change this fast.\n\n"
            f"Here's the angle we're watching: {idea}"
        )
        draft = (body + cta_line)[: ctx.max_length]
        return draft

    def hashtags(self, brand: BrandConfig, ctx: ContentContext) -> List[str]:
        base = [brand.industry, "LinkedInGrowth", "ThoughtLeadership"]
        topic_tag = "".join(w.capitalize() for w in ctx.topic.split()[:4])
        tags = [f"#{t.replace(' ', '')}" for t in base] + [f"#{topic_tag}"]
        # de-duplicate while preserving order
        seen = set()
        out = []
        for t in tags:
            if t.lower() not in seen:
                seen.add(t.lower())
                out.append(t)
        return out[:6]

    def review(self, draft: str, brand: BrandConfig) -> tuple[float, str]:
        score = 0.6
        notes = []
        length = len(draft)
        if 300 <= length <= 1200:
            score += 0.15
            notes.append("Length is well-suited for LinkedIn's feed algorithm.")
        else:
            notes.append("Consider trimming or expanding for optimal feed performance.")
        banned_hits = [w for w in brand.banned_words if w.lower() in draft.lower()]
        if banned_hits:
            score -= 0.3
            notes.append(f"Flagged banned terms: {', '.join(banned_hits)}.")
        else:
            score += 0.15
            notes.append("No banned or off-brand terms detected.")
        if brand.name.lower() in draft.lower():
            score += 0.1
            notes.append("Brand name is present, reinforcing recall.")
        score = max(0.0, min(1.0, round(score, 2)))
        return score, " ".join(notes)


class AutoGenAgents:
    """Real AG2 / AutoGen-backed agents, used when USE_MOCK=false.

    Mirrors the AssistantAgent + GroupChat + GroupChatManager pattern from
    the course notebook (AutoGen2003.ipynb), but scoped down to a
    lightweight sequential pipeline that is cheap and fast enough to sit
    behind a synchronous HTTP endpoint.
    """

    def __init__(self):
        import autogen  # local import: only required in non-mock mode

        self.autogen = autogen
        self.llm_config = {
            "config_list": [
                {"model": MODEL_NAME, "api_key": OPENAI_API_KEY}
            ],
            "temperature": 0.7,
        }

    def _run_agent(self, system_message: str, user_message: str) -> str:
        ideation_agent = self.autogen.AssistantAgent(
            name="Agent",
            system_message=system_message,
            llm_config=self.llm_config,
            human_input_mode="NEVER",
        )
        user_proxy = self.autogen.UserProxyAgent(
            name="Orchestrator",
            human_input_mode="NEVER",
            code_execution_config=False,
            max_consecutive_auto_reply=1,
        )
        user_proxy.initiate_chat(ideation_agent, message=user_message, max_turns=1)
        last_msg = user_proxy.last_message(ideation_agent)["content"]
        return last_msg.strip()

    def ideate(self, brand: BrandConfig, ctx: ContentContext) -> List[str]:
        out = self._run_agent(
            system_message=(
                "You are IdeationAgent, a LinkedIn content strategist for "
                f"{brand.name} ({brand.industry}). Voice: {brand.voice}. "
                "Return exactly 5 short post angles, one per line, no numbering."
            ),
            user_message=f"Topic: {ctx.topic}. Audience: {ctx.audience}. Goal: {ctx.goal}.",
        )
        ideas = [line.strip("-• ").strip() for line in out.splitlines() if line.strip()]
        return ideas[:5] or [ctx.topic]

    def draft(self, brand: BrandConfig, ctx: ContentContext, idea: str) -> str:
        out = self._run_agent(
            system_message=(
                "You are DraftingAgent. Write one LinkedIn post "
                f"(max {ctx.max_length} characters) in the brand voice: {brand.voice}. "
                "No hashtags in the body."
            ),
            user_message=f"Chosen angle: {idea}. Topic: {ctx.topic}. CTA: {ctx.cta or 'none'}.",
        )
        return out[: ctx.max_length]

    def hashtags(self, brand: BrandConfig, ctx: ContentContext) -> List[str]:
        out = self._run_agent(
            system_message="You are HashtagAgent. Return 4-6 relevant, "
                            "professional LinkedIn hashtags, space-separated, no explanation.",
            user_message=f"Topic: {ctx.topic}. Industry: {brand.industry}.",
        )
        return [t for t in out.split() if t.startswith("#")][:6]

    def review(self, draft: str, brand: BrandConfig) -> tuple[float, str]:
        out = self._run_agent(
            system_message=(
                "You are ReviewerAgent, a strict brand-compliance and quality "
                "reviewer. Respond ONLY as JSON: {\"score\": <0-1 float>, \"notes\": \"<text>\"}."
            ),
            user_message=f"Brand banned words: {brand.banned_words}. Draft:\n{draft}",
        )
        try:
            parsed = json.loads(out[out.find("{"): out.rfind("}") + 1])
            return float(parsed["score"]), str(parsed["notes"])
        except Exception:
            logger.warning("ReviewerAgent returned non-JSON output, defaulting score.")
            return 0.7, "Reviewer output could not be parsed; default score applied."


def get_agents():
    if USE_MOCK:
        return MockAgents(), "mock"
    try:
        return AutoGenAgents(), "autogen"
    except Exception as exc:  # missing package / missing key, etc.
        logger.error("Falling back to mock agents: %s", exc)
        return MockAgents(), "mock-fallback"


# --------------------------------------------------------------------------
# Logging (traceability requirement)
# --------------------------------------------------------------------------

def log_run(record: dict) -> None:
    try:
        with LOG_FILE.open("a") as f:
            f.write(json.dumps(record) + "\n")
    except Exception as exc:
        logger.error("Failed to write run log: %s", exc)


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "mode": "mock" if USE_MOCK else "autogen"}


@app.post("/linkedin", response_model=LinkedInResponse)
def generate_linkedin_post(payload: LinkedInRequest):
    run_id = str(uuid.uuid4())
    started = time.time()
    trace = []

    try:
        agents, mode = get_agents()
        trace.append(f"pipeline started (mode={mode})")

        ideas = agents.ideate(payload.brand, payload.context)
        trace.append(f"IdeationAgent produced {len(ideas)} idea(s)")

        chosen_idea = ideas[0] if ideas else payload.context.topic
        draft = agents.draft(payload.brand, payload.context, chosen_idea)
        trace.append("DraftingAgent produced draft")

        tags = agents.hashtags(payload.brand, payload.context)
        trace.append(f"HashtagAgent produced {len(tags)} hashtag(s)")

        score, notes = agents.review(draft, payload.brand)
        trace.append(f"ReviewerAgent scored confidence={score}")

    except Exception as exc:
        logger.exception("Pipeline failure for run_id=%s", run_id)
        log_run({
            "run_id": run_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "error",
            "error": str(exc),
            "duration_s": round(time.time() - started, 3),
        })
        raise HTTPException(status_code=500, detail=f"Agent pipeline failed: {exc}") from exc

    meets_threshold = score >= payload.min_confidence
    response = LinkedInResponse(
        run_id=run_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        ideas=ideas,
        draft=draft,
        hashtags=tags,
        confidence_score=score,
        meets_threshold=meets_threshold,
        reviewer_notes=notes,
        agent_trace=trace,
        mode=mode,
    )

    log_run({
        "run_id": run_id,
        "timestamp": response.generated_at,
        "status": "success",
        "brand": payload.brand.name,
        "topic": payload.context.topic,
        "confidence_score": score,
        "meets_threshold": meets_threshold,
        "dry_run": payload.dry_run,
        "duration_s": round(time.time() - started, 3),
        "draft_preview": draft[:120],
    })

    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), reload=True)
