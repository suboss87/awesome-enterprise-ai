"""Score use-case candidates against docs/RUBRIC.md with Jev (TypeSafe System One).

Usage:
    TYPESAFE_API_KEY=... python3 tools/score_candidates.py docs/candidates.json [--write docs/CANDIDATES.md]

Input: a JSON list of candidate sheets:
    {"name": "...", "function": "...", "owner_role": "...", "evidence": "free text with numbers and sources",
     "sources": ["https://..."], "existing_projects": ["ap-exception-agent", ...]}

The model answers one Score question per criterion over the whole sheet. Thresholds live here, not in
the prompt: total >= 38/50, no criterion below 3, diversity >= 4. Answers with confidence below 0.5 are
marked for a human read. Stdlib only.
"""
import argparse
import json
import os
import sys
import urllib.request

ENDPOINT = 'https://api.typesafe.ai/v1/systemone'
MODEL = os.environ.get('TYPESAFE_MODEL', 'jev-latest')
MIN_TOTAL = 38
MIN_EACH = 3
MIN_DIVERSITY = 4
LOW_CONFIDENCE = 0.5

LEVELS = ['1', '2', '3', '4', '5']
CRITERIA = {
    'acute_pain': ('How acute and measurable is the pain this workflow addresses today, according to the sheet?',
                   ['Nice to have; no cost named', 'A cost exists but is not quantified', 'A known cost center, rough numbers',
                    'Quantified cost with one public source', 'Measured cost today (volume, minutes, wage, penalties or leakage) with public numbers']),
    'code_decides': ('Can eligibility, thresholds, matching and routing be deterministic code, with the model only reading, extracting, classifying or drafting?',
                     ['The model must judge eligibility, amounts or liability', 'Most decisions need model judgment', 'Mixed: some rules, some judgment',
                      'Rules decide; the model classifies and drafts with a few judgment calls', 'Rules decide everything that matters; the model only reads, extracts, classifies, drafts']),
    'approval_fits': ('Does the output fit naturally as a proposal into an approval queue that already exists?',
                      ['The value requires autonomous writes', 'Approval would remove most of the value', 'Approval is possible but awkward',
                       'A proposal into a queue fits well', 'The proposal lands in an existing ERP, ticketing, CRM or GRC queue by design']),
    'data_reachable': ('Can the inputs be drawn from standard systems and imitated faithfully by a seeded synthetic generator?',
                       ['Needs proprietary feeds or live human interaction', 'Hard to imitate', 'Standard systems but complex formats',
                        'Standard exports, emails, PDFs or logs that a generator imitates reasonably', 'Plain documents, exports, logs or tickets a generator imitates faithfully']),
    'measurable': ('Is there a natural labeled golden set, a practitioner-reported metric, and a non-AI baseline?',
                   ['No natural label', 'Labels possible, metric unclear', 'A metric exists but no baseline',
                    'Metric and baseline exist', 'Practitioners already report the metric (straight-through rate, recall, cycle time, cost per item) and a rules baseline is natural']),
    'adoption_evidence': ('How strong is the public evidence of production use with numbers?',
                          ['Vendor marketing only', 'One vendor claim', 'One credible independent source', 'Two sources, one with numbers',
                           'Two or more independent public sources with production numbers']),
    'roi_mechanism': ('How explicit and credible is the ROI mechanism (who saves what, quoted with a source)?',
                      ['Vague productivity', 'Plausible but unquantified', 'Quantified by a vendor only', 'Quantified with a source',
                       'Explicit, quoted numbers from a credible source, mechanism clear']),
    'not_generic': ('Is this a specific operational workflow with a named owner role and hard edge cases, rather than a generic chatbot or summary tool?',
                    ['Chatbot over documents or meeting summaries', 'Generic assistant', 'Specific but common tutorial material',
                     'Specific workflow with an owner role', 'Named workflow, named owner role, hard edge cases listed']),
    'buildable_simply': ('Can this be one agent with 5 to 8 tools on a stdlib runtime, replayable, without orchestration frameworks, vector databases or fine-tuning?',
                         ['Needs orchestration, vector DB or fine-tuning', 'Several services required', 'One agent but many tools or heavy integration',
                          'One agent, 5 to 8 tools, light integration', 'One agent, 5 to 8 tools, stdlib runtime, trivially replayable']),
    'diversity': ('How different is this from the existing projects listed in the sheet (industry and function)?',
                  ['Duplicates an existing project', 'Same industry and similar task', 'Same industry, different task',
                   'New function in a covered industry', 'New industry or new function for the repo']),
}


def ask_jev(state, questions, key):
    body = json.dumps({'model': MODEL, 'state': state, 'questions': questions}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method='POST',
                                 headers={'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.load(resp)['answers']


def score_candidate(candidate, key):
    questions = {name: {'type': 'score', 'instructions': f'{instructions} Rate 1 (worst) to 5 (best) using the levels.',
                        'criteria': levels} for name, (instructions, levels) in CRITERIA.items()}
    answers = ask_jev(candidate, questions, key)
    scores = {}
    for name, ans in answers.items():
        # score is the probability-weighted position on the 0-based levels; shift to 1..5
        scores[name] = {'score': round(float(ans['score']) + 1, 2), 'confidence': round(float(ans.get('confidence', 1.0)), 2)}
    total = round(sum(v['score'] for v in scores.values()), 1)
    low = [n for n, v in scores.items() if v['confidence'] < LOW_CONFIDENCE]
    verdict = 'build' if (total >= MIN_TOTAL and all(v['score'] >= MIN_EACH for v in scores.values())
                          and scores['diversity']['score'] >= MIN_DIVERSITY) else 'hold'
    return {'name': candidate['name'], 'total': total, 'scores': scores, 'verdict': verdict, 'needs_human_read': low}


def render(results):
    cols = list(CRITERIA)
    head = '| Candidate | Total /50 | ' + ' | '.join(c.replace('_', ' ') for c in cols) + ' | Verdict |\n'
    head += '|---|---:|' + '---:|' * len(cols) + '---|\n'
    rows = ''
    for r in sorted(results, key=lambda r: -r['total']):
        cells = ' | '.join(f"{r['scores'][c]['score']:.1f}" + ('*' if c in r['needs_human_read'] else '') for c in cols)
        rows += f"| {r['name']} | {r['total']} | {cells} | {r['verdict']} |\n"
    note = ('\nScores are Jev (TypeSafe System One) Score answers, 1 to 5, probability-weighted. `*` marks confidence below 0.5: a '
            f'person reads that criterion. Thresholds in `tools/score_candidates.py`: total >= {MIN_TOTAL}, every criterion >= {MIN_EACH}, '
            f'diversity >= {MIN_DIVERSITY}.\n')
    return head + rows + note


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('candidates')
    parser.add_argument('--write', help='Markdown file to write the table into (replaces the block between <!-- scores --> markers)')
    args = parser.parse_args()
    key = os.environ.get('TYPESAFE_API_KEY')
    if not key:
        print('Set TYPESAFE_API_KEY', file=sys.stderr)
        return 2
    candidates = json.load(open(args.candidates))
    results = [score_candidate(c, key) for c in candidates]
    table = render(results)
    print(table)
    if args.write:
        path = args.write
        text = open(path).read() if os.path.exists(path) else '# Candidates\n\n<!-- scores -->\n<!-- /scores -->\n'
        start, end = text.index('<!-- scores -->') + len('<!-- scores -->'), text.index('<!-- /scores -->')
        open(path, 'w').write(text[:start] + '\n' + table + text[end:])
    return 0


if __name__ == '__main__':
    sys.exit(main())
