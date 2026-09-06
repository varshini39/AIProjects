# Agentic RAG: Router-Retriever System with PDF and Web Search Tools

Course-end project — a CrewAI-based multi-agent system that routes a natural
language question to the retrieval path best suited to answer it: a static
PDF vector search (`crewai_tools.PDFSearchTool`), a live web search
(`TavilySearchResults`), or a direct LLM answer with no retrieval at all.

## Folder structure

```
agentic_rag_router/
├── data/
│   └── attention_is_all_you_need.pdf   # domain-specific static document
├── AgenticRAG_Project.ipynb            # main deliverable notebook
├── outputs/
│   └── reasoning_trace_log.csv         # generated after running the notebook
├── requirements.txt
└── README.md
```

## System architecture

```
User question
     |
     v
+--------------------------+
|  Router Agent (Crew #1)  |   classifies into: PDF_VECTOR_SEARCH | WEB_SEARCH | DIRECT_ANSWER
+--------------------------+
     |
     v
Retriever Agent is built for this question with ONLY the matching tool bound:
  PDFSearchTool (crewai_tools)  |  TavilySearchResults  |  no tool
     |
     v
+-----------------------------------------------+
|  Retriever Agent -> Answer Generation Agent    |   (Crew #2, 2 chained tasks)
+-----------------------------------------------+
     |
     v
Final answer + reasoning trace log entry
```

### Agent roles and responsibilities

**Router Agent**
- Input: the raw user question
- Output: free-text response whose first line is one of three exact
  labels — `PDF_VECTOR_SEARCH`, `WEB_SEARCH`, or `DIRECT_ANSWER` — plus a
  short reason
- Responsibility: classification only. `classify_question()` parses the
  label out of the agent's text output so the rest of the pipeline can
  branch on it reliably.

**Retriever Agent**
- Built fresh for every question by `make_retriever_agent(route)`, with
  exactly one tool bound to it based on the Router's decision:
  - `PDF_VECTOR_SEARCH` -> `crewai_tools.PDFSearchTool(pdf=PDF_PATH)`,
    which performs its own semantic search restricted to the uploaded
    "Attention Is All You Need" PDF
  - `WEB_SEARCH` -> `TavilySearchResults` (LangChain), wrapped in a small
    `crewai.tools.BaseTool` subclass -- CrewAI validates every entry in an
    agent's `tools` list against its own `BaseTool` class, so a raw
    LangChain tool object can't be passed in directly
  - `DIRECT_ANSWER` -> no tool at all
- Output: relevant evidence gathered using its tool (or, for
  `DIRECT_ANSWER`, from its own knowledge), with source page/URL noted
  when available
- Because it only ever has the one relevant tool, it cannot accidentally
  search the wrong source.

**Answer Generation Agent**
- Input: the question and the Retriever Agent's evidence, chained in via
  `context=[task_retriever]`
- Output: the final, source-grounded answer
- Responsibility: writes the user-facing answer, explicitly instructed to
  use only the Retriever Agent's evidence, cite pages/URLs where available,
  and say so if the answer isn't in the evidence rather than guessing.

### Coordination flow

1. `classify_question(question)` runs a single-task **Router Crew** and
   parses its output into one of three route labels.
2. `make_retriever_agent(route)` builds a Retriever Agent with only the
   tool matching that route bound to it (`PDFSearchTool`,
   `TavilySearchResults`, or none).
3. That agent, plus the Answer Generation Agent, run in a **second Crew**
   with two tasks chained via `context=[task_retriever]`, so the Answer
   agent sees the Retriever agent's gathered evidence.
4. Every question's route, router reasoning, tool used, the Retriever
   Agent's evidence (`result.tasks_output[0].raw`), and the Answer
   Generation Agent's final output (`result.tasks_output[-1].raw`) are
   appended to `trace_log` as separate fields — so each agent's individual
   contribution is inspectable, not just a single merged answer — later
   exported as `outputs/reasoning_trace_log.csv`.

## Why CrewAI

CrewAI was selected as the orchestration framework (as required by the
brief) over hand-rolling the router/retriever logic with raw LLM calls,
because it provides:
- **Role-based `Agent` objects** that map directly onto the "Router Agent"
  and "Retriever Agent" roles named in the brief, each with its own goal,
  backstory, and bound tools, keeping responsibilities cleanly separated
- **Native tool binding** (`Agent(tools=[...])`) — CrewAI handles the
  tool-calling loop for `PDFSearchTool` and `TavilySearchResults`
  internally, so no hand-written function-calling boilerplate is needed
- **`Task` objects with `context=[...]` chaining**, so one agent's output
  is automatically passed as input to the next — this is what implements
  the "clear input-output flow" between agents the brief asks for
- **A `Crew` that returns per-task outputs** (`result.tasks_output`),
  which is what makes it possible to log each agent's individual
  contribution to the reasoning trace, not just a single merged answer
- **Built-in verbose execution logs**, giving a ready-made view into each
  agent's reasoning as it runs, on top of the trace log this notebook builds

## Why two Crews instead of one

CrewAI's standard `Crew` + `Process.sequential` pipeline does not support
conditional branching mid-pipeline — that exists only in the separate,
heavier CrewAI *Flows* feature. Because the Retriever Agent's tool has to
be decided by the Router *before* that agent can even be constructed, this
notebook splits the pipeline into:
1. A small **Router Crew** (one agent, one task) that only decides the route
2. A **Retriever + Answer Crew**, built afterward with the Retriever Agent
   already scoped to the correct tool

This keeps each agent's responsibility narrow and the control flow fully
visible in plain Python between the two Crews, at the cost of not using one
unified Crew for the whole pipeline.

## Challenges faced

- **Parsing a free-text router decision reliably.** Rather than a
  structured Pydantic output type, the Router task is instructed to put an
  exact label on its first line, and `classify_question()` does a simple
  case-insensitive keyword match. This is simple to read and debug, at a
  small cost in robustness — an unusual phrasing from the LLM could in
  principle omit the label, which is why the fallback defaults to
  `DIRECT_ANSWER` rather than raising an error.
- **Scoping the Retriever Agent's tools per question.** Giving the
  Retriever Agent every tool up front and trusting the LLM to pick the
  right one risked it calling the wrong tool or mixing PDF and web
  evidence. Building a fresh agent per question with only the single
  relevant tool removes that ambiguity entirely.
- **Avoiding hallucination on out-of-scope questions.** The Answer task
  explicitly instructs the agent to say so if the answer isn't in the
  Retriever Agent's evidence — demonstrated in the demo with a question the
  paper doesn't cover (its "stance on quantum computing").

## Running the notebook

1. `pip install -r requirements.txt`
2. `cp .env.example .env` in this folder, then add your `OPENAI_API_KEY`
   and `TAVILY_API_KEY` (a free Tavily key is available at
   https://tavily.com). The notebook loads `.env` from its own working
   directory, so launch Jupyter from this folder (`cd
   CrewAI/agentic_rag_router && jupyter notebook ...`) or make sure your
   editor runs the notebook with this folder as its working directory.
3. Open `AgenticRAG_Project.ipynb` in VS Code or Jupyter and run all cells
   top to bottom
4. The demo section runs 5 sample questions (2 PDF-routed, 1 web-routed, 2
   direct, 1 out-of-scope) and prints each agent's reasoning as it executes
5. The final cells display the reasoning trace as a table and save it to
   `outputs/reasoning_trace_log.csv`

