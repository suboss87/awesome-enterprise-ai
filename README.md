<div align="center">

# Awesome Enterprise AI

### Business problems. Working solutions. Clear paths to adoption.

Practical projects for teams bringing AI into everyday operations.

[Explore projects](#explore-projects) · [Start using one](ADOPTION.md) · [Contribute a problem](CONTRIBUTING.md)

</div>

---

## Built around the work

Finding the right policy. Checking a document before it enters a business system. Handling the exceptions an automated workflow cannot resolve.

I’m building this collection around those everyday problems: who gets stuck, what it costs them, and where a small piece of software can help. Each project includes a clear use case, runnable examples, tests, and the boundaries you need to understand before adopting it.

## Explore projects

### 01 / Trusted knowledge

**[RAG Scope Check →](projects/rag-scope-check/)**

*Help employees find the information they are entitled to use.*

An assistant can avoid exposing restricted documents and still miss the answer its user needs. This project checks both sides: information stays within permission boundaries, and useful answers remain discoverable.

- **Who it helps:** teams maintaining internal assistants, policy search, or support knowledge.
- **Where it fits:** employee self-service, banking operations, manufacturing support, and shared services.
- **Try it:** reproduce a missing-policy failure, correct the permission copy, and compare the results.
- **Available today:** a local checker and tested SQLite example. Real source-system integration remains open.

[Run the example](projects/rag-scope-check/#run-it) · [Project code](https://github.com/suboss87/rag-scope-check)

---

## What you get in every project

| Your question | Where to look |
|---|---|
| What problem does this solve? | Business problem and intended users |
| How does the work change? | Before-and-after workflow |
| Can I try it? | Quickstart, sample inputs, and expected outputs |
| Can my team adopt it? | Integration contract, data handling, and deployment limits |
| Does it work? | Tests, reproducible evidence, and independent review |

Projects are designed for workflows that recur across industries. Industry examples describe potential uses; they are not customer endorsements or claims of regulatory approval.

## Start with a small trial

1. Choose the business problem that matches your workflow.
2. Run the included example with synthetic data.
3. Test representative cases inside your own environment.
4. Connect your systems only after reviewing permissions, data handling, and failure behavior.

[Read the adoption guide →](ADOPTION.md)

## How the collection grows

Research starts with recurring user problems. Ideas are compared with existing solutions and challenged with Jev before a focused build. Each release gets tests, documentation, and a separate review. Daily work can add a project or improve one already here.

**Available** means the documented example runs and its checks pass. It does not mean a project has been validated in your environment. Project pages state what has been tested and what remains open.

[Verification runs](https://github.com/suboss87/awesome-enterprise-ai/actions/workflows/verify.yml) · [Suggest a problem](CONTRIBUTING.md) · [Report a vulnerability](SECURITY.md)

---

Built by [Subash Natarajan](https://github.com/suboss87) · [MIT license](LICENSE)
