# Contributing

Start with a problem report in an issue:

1. Who is affected, and what were they trying to do?
2. What actually failed? Include a minimal, sanitized reproduction.
3. Which existing solutions did you try, and what specific gap remains?
4. What observable result would make this useful?

Do not include credentials, customer records, private documents or confidential logs. Report vulnerabilities through [private security reporting](https://github.com/suboss87/awesome-enterprise-ai/security/advisories/new).

For a project contribution, use a stable `projects/<problem-slug>/` folder. Include a README with the business problem, intended users, workflow, runnable quickstart, expected failure/success, tests and limits. Keep one canonical source location. If code lives in another repository, pin the revision used by this collection and add its actual tests and demo to CI.

Each project also needs a `GOVERNANCE.md` that names the intended business owner and reviewer, defines permitted actions, identifies sensitive data and source authority, and sets out the domain-specific acceptance evidence. Use the smallest controls that address the actual risk. A read-only review aid and a system that changes entitlements have different obligations.

Keep executable evaluation cases beside the implementation. Record how labels were produced, what was frozen before inference, which cases are development regressions, and which were independently held out. Compare useful outcomes and review effort against the existing process. Declare failure thresholds before viewing results; missing representative cases stay an explicit adoption gap.

Use the [quality rubric](quality/README.md) to prioritize improvements and retain unfavorable assessments. Production status requires the separate deployment gates, including actual source authorization and operator acceptance. A score, project count or renamed fork cannot supply that evidence.

New code must include its license and preserve attribution for reused work. Review should verify the result independently; a model rating or a green documentation check does not replace running the project. Avoid claims of adoption, enterprise readiness or uniqueness without evidence.

Maintainers review one focused change at a time. Research that rules out a duplicate or unsupported idea is useful too.
