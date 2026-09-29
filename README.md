# Awesome Enterprise AI

**Small, inspectable tools for the parts of enterprise AI that break.**

I build these projects to understand a problem deeply enough to make something useful. Each starts with a reported failure, a look at existing solutions, and a result someone else can reproduce. The collection starts with retrieval permissions; agent workflows and deployment reliability are areas I am investigating.

[Browse projects](#projects) · [Run the first project](projects/rag-scope-check/README.md#run-it) · [Suggest a problem](CONTRIBUTING.md)

## Projects

### Retrieval and permissions

| Project | When it helps | Evidence today |
|---|---|---|
| [RAG Scope Check](projects/rag-scope-check/) | Your retrieval passes leak checks but misses documents a user should be able to read | Executable SQLite stale-permission failure and correction; automated regression tests. **Experimental; synthetic fixture.** |

Each folder explains the problem, the approach, how to run it, and its limits. RAG Scope Check has its own [source repository](https://github.com/suboss87/rag-scope-check); the guide pins a tested revision so the code has one maintained home.

## Start with a failure

The first example reproduces an index whose permission copy is stale. It returns public context safely but omits the useful private answer. Synchronizing that copy restores the answer without loosening access or changing the test thresholds.

| Same query and source permissions | Authorized recall | Underfill | Leaked documents | Gate |
|---|---:|---:|---:|---|
| Stale index permission copy | 0% | 100% | 0 | Fail |
| Synchronized copy | 100% | 0% | 0 | Pass |

These are measurements from a deliberately planted SQLite fixture, not a customer deployment or a performance benchmark. [Reproduce both states →](projects/rag-scope-check/)

## How projects earn a place

- An identifiable user and a concrete failure, with original sources.
- A comparison with existing tools. Fix upstream when that is the better home.
- A focused implementation and a reproducible result, including the failure case.
- Tests, setup instructions, a license, and explicit limits.
- A separate review before publication. Jev helps challenge the evidence and scope; its judgment is advisory.

Research and development run daily. A day may produce a new project, improve an existing one, or reject an idea. Publication follows working evidence rather than a daily quota.

[Daily verification](https://github.com/suboss87/awesome-enterprise-ai/actions/workflows/verify.yml) runs the first project's tests and failure/correction demo at a pinned revision. It verifies that recorded example; it does not certify a live deployment or monitor upstream changes automatically.

## Contribute a problem

Show the failure, the workaround, and what you have already tried. Remove customer data and secrets. [Contribution guide →](CONTRIBUTING.md)

Organization inspired by [Awesome LLM Apps](https://github.com/Shubhamsaboo/awesome-llm-apps): clear project folders and direct quickstarts. This collection's code, selection criteria, and explanations are developed independently.

Built by [Subash Natarajan](https://github.com/suboss87). [MIT license](LICENSE).
