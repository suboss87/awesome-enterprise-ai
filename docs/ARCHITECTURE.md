# Architecture

One small runtime, five agents, no framework. About 900 lines of standard-library Python carry everything shared.

```
                 ┌──────────────────────────────────────────────────────────┐
  input JSON ───►│ projects/<agent>/agent.py                                 │
  (records,     │  validate(data)  → input contract, rejects unknown fields  │
   documents)   │  build_tools()   → read tools over the records             │
                 │  Agent.run()     → enterprise_ai/agent.py                  │
                 │     ┌───────────────────────────────────────────────┐     │
                 │     │ loop ≤ max_steps                              │     │
                 │     │  provider.complete(system, messages, tools)   │◄────┼── enterprise_ai/llm.py
                 │     │  tool_use → validate input → execute (reads)  │     │   anthropic | openai | replay
                 │     │           → record proposal (writes)          │     │
                 │     │  finish   → validate schema + evidence quotes │     │
                 │     └───────────────────────────────────────────────┘     │
                 │  rules (matching.py, triage.py, …) → final decision        │
                 │  build_output() → summary, metrics, findings, actions      │
                 └──────────────────────────────────────────────────────────┘
                                   │ trace (gen_ai.* events, cost, latency)
                                   ▼
        CLI `run` · web workspace · `eval` runner (agent vs baseline → evals/REPORT.md)
```

## The division of labour

| The model | The code |
|---|---|
| Reads documents in any layout, classifies them, extracts fields, notices pressure or embedded instructions, drafts messages, ranks hypotheses, writes justifications. | Validates every input and tool call, joins records, applies tolerances and policies, computes the route or the ranking, enforces evidence quotes, refuses to execute writes. |

A model recommendation is logged next to the rules' decision. When they disagree, that is a review signal, not a tie-break for the model.

## Runtime modules

| Module | Responsibility | Size |
|---|---|---|
| `llm.py` | `AnthropicProvider` (Messages API, strict tools, effort), `OpenAIProvider` (Responses API, strict function tools), `ReplayProvider`, `RecordingProvider`, price table, cost estimate. Canonical message shape is Anthropic-like; the OpenAI adapter converts. | ~230 lines |
| `agent.py` | `Agent`, `Tool`, `Trace`. The loop, the approval gate, the `finish` validation, the data boundary text. | ~170 lines |
| `common.py` | Input validation helpers, strict JSON loading, schema validation, verbatim evidence check. | ~190 lines |
| `runner.py` | `execute(slug, data, provider)` used by CLI, web and evals. Attaches the `execution` block. | ~50 lines |
| `evals.py` | Runs agent and baseline on `cases.jsonl` in parallel, aggregates metrics, renders `REPORT.md`. | ~170 lines |
| `catalog.py`, `server.py`, `web/` | Allowlist of agents, loopback HTTP workspace with CSP and a per-session token. | ~200 lines |

## Request shape to the providers

Anthropic: `POST /v1/messages` with `system`, `messages`, `tools` (each with `strict: true`, `additionalProperties: false`), `output_config.effort`. Thinking stays at the model default (adaptive). OpenAI: `POST /v1/responses` with `instructions`, `input` items, function tools with `strict: true`, `store: false`. Both return tool calls that the loop executes or records. The final answer always arrives through the `finish` tool, so the result schema is enforced identically on both providers.

## What is deliberately absent

No vector database, no orchestration framework, no background queue, no multi-agent handoffs. Each agent needs at most a dozen tool calls over records that fit in context. When an adopter's records do not fit, the right change is a narrower read tool, not a bigger prompt.
