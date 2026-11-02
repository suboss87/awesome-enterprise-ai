# Deployment boundary

These agents run as a library or CLI inside your environment. They do not call your systems; you pass them the records.

## Data flow

1. Your adapter reads the records one case needs (one invoice and its PO, one ticket and its order, one incident window) and builds the input JSON.
2. The agent sends the system prompt, the records and tool results to the configured provider. Nothing else leaves your environment.
3. The result, trace and proposed actions return to your adapter. You store them under your retention policy and route proposals to your approval queue.

## Providers and keys

`ANTHROPIC_API_KEY` (default provider) or `OPENAI_API_KEY`. `LLM_PROVIDER` selects when both are set. `ANTHROPIC_MODEL` / `OPENAI_MODEL` override the model. Keys are read from the environment only and never appear in results or traces. Check your provider's data-retention terms; the Anthropic requests use the standard API and the OpenAI requests set `store: false`.

## Minimum controls before an operational trial

- Run behind your identity provider; the local workspace is a single-user preview on the loopback interface, not an authentication boundary.
- Minimise personal data in inputs. The agents need business identifiers, not people's details, except where the task is about a person (claims, support).
- Keep the approval queue outside the agent. Nothing in this collection executes a write.
- Set a per-run deadline in your adapter. The runtime bounds steps and tool output, not wall-clock time across providers.
- Log the `execution` block with the business record. It carries the model id, response ids, tool calls, token counts and the input hash.

## Container

A hardened image is a few lines: `python:3.13-slim`, copy the repository, run as a non-root user, read-only filesystem, no network except the provider. The CI job runs every example and baseline eval offline; a live eval needs a key as a secret.
