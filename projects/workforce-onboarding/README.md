# Onboarding Readiness Desk

HR and IT coordinators check whether a new starter's recorded tasks and prerequisites are ready. AI interprets role/location policies; deterministic dependency checks prevent a completed downstream task from hiding unfinished prerequisites.

## Try it

From the repository root:

```sh
python3 -m enterprise_ai run workforce-onboarding --input projects/workforce-onboarding/examples/input.json --mode replay --responses projects/workforce-onboarding/examples/responses.json
python3 -m unittest discover -s projects/workforce-onboarding/tests -v
```

Replay uses hand-authored responses. Set `OPENAI_API_KEY` and use `--mode live` without `--responses` for actual model interpretation. Python standard library only; no identity provider or provisioning connector is required.

## Business flow

1. Supply one starter, the applicable policy excerpts and current task records with named owners.
2. AI maps each task to required, optional or uncertain policy applicability and quotes its evidence.
3. Rules preserve required flags, follow dependency chains, reject cycles and unknown tasks, and detect inconsistent completion records.
4. Coordinators receive readiness blockers and an owner queue. No access is created or removed.

The example has completed identity verification and pending repository access. Marking repository access complete makes the recorded checklist ready only if its prerequisite is also complete and policy applicability is settled.

## Input contract

- `as_of`: ISO assessment date.
- `starter`: `id`, `role`, `location`, ISO `start_date`.
- `policies`: up to 100 unique `id`/`text` records. Text is limited to 10,000 characters. Supply authoritative, current policy excerpts.
- `tasks`: 1–100 unique records with `id`, `title`, `owner`, `status` (`pending`, `blocked`, `complete`), boolean `required`, and a list of prerequisite task IDs in `depends_on`.

Unknown fields, duplicate/unknown dependencies, dependency cycles, omitted model matches and fabricated evidence are rejected. Required flags cannot be downgraded by model output. Dependencies of required tasks also become required. An uncertain policy match blocks readiness even if a task is recorded complete.

## Readiness is conditional on the supplied records

`metrics.ready` means this supplied checklist has no unresolved required tasks, uncertain policy matches or inconsistent completion dependencies. It does not prove accounts exist, verify identity, show that approvals were authentic, or establish that the checklist covers every legal/organizational requirement.

`actions` lists unfinished tasks by owner and prerequisite. `policy_matches` retains quoted interpretations. `provisioning_performed` is always false. AI maps text to tasks; graph traversal and readiness are deterministic. A quote match proves presence, not correct policy interpretation.

## Evaluation

Ten frozen synthetic cases cover day-one blockers, completed records, false completion, downgrade attempts, required dependency closure, policy uncertainty, cycles, unknown prerequisites, fabricated quotes and omitted tasks. Replay tests validate these safety/business rules, not live policy accuracy.

Compare live policy mapping to a maintained role checklist and dependency graph on independently labeled policies and starters. Measure false-ready decisions, missing mandatory tasks, inappropriate optional labels, unnecessary clarification and coordinator correction time. There is no HR-system integration or enterprise validation yet.

## Adoption

An authorized HR/IT operator must select applicable policy and current task exports. Authenticate the user, isolate each starter's records and minimize personal data before invoking this workflow. Live mode transmits supplied text to the model provider. Completion updates, identity checks and provisioning remain in your existing approved systems.
