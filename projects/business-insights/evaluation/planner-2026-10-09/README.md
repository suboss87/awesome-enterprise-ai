# Does the planner preserve the business question?

Twelve independently authored synthetic questions were labeled and reviewed
before any inference. The records are the collection's fictional sales example,
with one declared currency variant. Labels include exact arithmetic, record IDs,
effective dates, filters and whether an answer should be withheld. This is a
small development study, not representative analyst or domain-owner acceptance.

The original corpus SHA256 is
`5962a87c8b8099d2b5ba3c14c106dd9263eec4dadd0cd281971dbbd87730f7cc`.
It remains unchanged. The runner freezes cases, model and source hashes before
calls; all twelve attempted live calls and their provider responses are retained.
The final source hashes match the initial ones. The original source snapshots
in `trial/source/` reproduce those hashes, including the workflow before the
correction described below. They are historical evidence, not current code.

## Results before the correction

| Method | Strict normalized plans | Correct answer state | False calculations on six withheld cases |
|---|---:|---:|---:|
| Supplied-plan oracle | 12/12 | 12/12 | 0/6 |
| Narrow lexical rules | 11/12 | 11/12 | 0/6 |
| Live planner | 10/12 | 11/12 | 1/6 |

The live model was `gpt-5.5-2026-04-23`, with medium reasoning and the collection's
fixed structured-output schema. Mean observed live latency was 4.519 seconds;
rules averaged 0.0009 seconds in this local run. Twelve calls completed without
transport failures. Provider IDs and actual token usage are in the retained
responses and [report](trial/report.json); no monetary cost or human time savings
is inferred from them.

The rules parser was developed with visible questions. It recognizes a narrow
set of lexical measures, calendar periods and filters, and conservatively asks
for clarification otherwise. It refused the explicit gross-profit question
because that question also mentions a percentage calculation in the negative.
Its score is not blind baseline performance. The supplied-plan oracle checks
arithmetic given a correct plan; it is not a human analyst performance measure.

Unknown-region clarification was predeclared safe-equivalent withholding, while
still failing strict ready-plan agreement. Mixed-currency clarification was the
only other permitted equivalence. No labels were changed after inference.

## What failed and what changed

For “How profitable were we in September 2026?” the live planner guessed
`gross_profit` and returned USD750.00. Profitability could mean a margin,
operating profit or another business definition. The failed response remains in
[the original case](trial/09-live/output.json).

Current workflow code withholds generic profitable/profitability or plural-profits
language and negated gross-profit requests before inference. Bare profit language
requires an explicit gross-profit mention or the supported deduction formula.
These conservative lexical checks may request clarification on otherwise valid
phrasing; they do not prove arbitrary language is unambiguous. Regression checks
include the observed failure, fresh wording variants and preservation of explicit
gross-profit calculations. This repairs
a demonstrated failure with a deterministic rule. It does not establish general
semantic correctness. No new live pass or improved live accuracy is claimed.

The study does not demonstrate a safety or broad usefulness advantage for the
live planner over these rules. Use an explicit reviewed plan or a constrained
question format for higher-assurance calculations until representative evidence
supports a wider language interface.

## Reproduce

From the collection root, offline:

```sh
python3 scripts/evaluate_business_planner.py --cases projects/business-insights/evaluation/planner-2026-10-09/cases.json --output /tmp/planner-offline-new --offline
python3 -m unittest discover -s tests -p test_business_planner_evaluation.py -v
```

The output directory must be new. Omit `--offline` only for an authorized new
live study with the server's provider key. That evaluates current code and
cannot reproduce the stochastic historical responses. Never repeat calls merely
to obtain a better score. Fresh representative holdouts, metric ownership,
source authorization and business acceptance still need an adopter.
