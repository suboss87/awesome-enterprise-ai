"""Rules-only baseline in the style of a keyword clause checklist.

A legal ops team without a model writes one regex or keyword per playbook topic: "mutual"
in the title or "each party" in the text, the first duration near "continue" or "survive",
"residual" or "unaided memory", "solicit" or "hire", the last place name in the sentence
that mentions governing law or jurisdiction, "renew" with a notice period, a cap multiple
in the sentence that limits liability, and a short blocklist for instructions aimed at a
reviewer. Each hit is quoted verbatim. The terms then go through the same `playbook.py`
rules as the agent, and every counsel or walk-away deviation gets the playbook fallback as
its redline, so the comparison isolates the reading step.
"""
import importlib.util
import re
from decimal import Decimal
from pathlib import Path

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('contract_playbook_b', _here/'playbook.py')
playbook = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(playbook)
_aspec = importlib.util.spec_from_file_location('contract_agent_b', _here/'agent.py')
agent_module = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(agent_module)

INJECTION = re.compile(r'automated review|AI reviewer|ignore (?:your|the|all) (?:playbook|instructions)|review tool', re.I)
PLACE = re.compile(r'[A-Z][a-z]+(?: (?:and )?[A-Z][a-z]+)*')
NOT_PLACES = {'Each', 'Any', 'The', 'This', 'Agreement', 'Customer', 'Supplier', 'Recipient', 'Discloser', 'Section', 'State', 'Court',
              'Chancery', 'Services'}
WORD_NUMBERS = r'\((\d+)\)'


def sentence(pattern, text, flags=re.I):
    """First sentence (verbatim, up to the full stop) that matches the pattern. Headings are skipped."""
    for m in re.finditer(r'[^.\n]*(?:' + pattern + r')[^.\n]*\.?', text, flags):
        candidate = m.group(0).strip()
        if len(candidate.split()) >= 5 and re.search(r'[a-z]', candidate):
            return candidate
    return None


def last_place(quote):
    places = [p for p in PLACE.findall(quote) if p not in NOT_PLACES]
    return places[-1] if places else None


def read_terms(contract):
    text, kind = contract['text'], contract['type']
    terms = []

    def add(topic, value, quote):
        if quote:
            terms.append({'topic': topic, 'value': str(value), 'quote': quote})

    if kind == 'NDA':
        title = text.strip().splitlines()[0]
        if 'MUTUAL' in title.upper():
            add('mutuality', 'mutual', title)
        else:
            quote = sentence(r'\beach party\b', text)
            add('mutuality', 'mutual' if quote else 'one_way', quote or sentence(r'Recipient', text))
        quote = sentence(r'in perpetuity|indefinitely', text)
        if quote:
            add('term', 'perpetual', quote)
        else:
            quote = sentence(r'(?:continue|remain|survive|period|term)[^.\n]{0,120}?' + WORD_NUMBERS + r'\s*(?:months?|years?)', text)
            if quote:
                m = re.search(WORD_NUMBERS + r'\s*(months?|years?)', quote)
                add('term', int(m.group(1)) * (12 if m.group(2).startswith('year') else 1), quote)
        quote = sentence(r'does not include|do not apply to information', text)
        add('exclusions', 'overbroad' if quote and re.search(r'discretion', quote) else 'standard', quote)
        add('residuals', 'present', sentence(r'residual|unaided memory', text))
        quote = sentence(r'solicit|\bhire\b', text)
        if quote and not re.search(r'does not restrict', quote):
            add('non_solicit', 'present', quote)
    quote = sentence(r'\bgovern(?:s|ed)?\b', text)
    if quote and last_place(quote):
        add('governing_law', last_place(quote), quote)
    quote = sentence(r'jurisdiction of|brought only in|courts? (?:located|sitting)', text)
    if quote and last_place(quote):
        add('venue', last_place(quote), quote)
    quote = sentence(r'\brenews?\b', text)
    if quote:
        notice = re.search(WORD_NUMBERS + r"\s*days", quote)
        add('auto_renewal', 'none' if re.search(r'does not renew', quote) else (notice.group(1) if notice else 'no_notice'), quote)
    if kind == 'MSA':
        cap = sentence(r'liability[^.\n]*(?:shall not exceed|is limited to)', text)
        if cap:
            multiple = Decimal(1)
            times = re.search(WORD_NUMBERS + r'\s*times', cap)
            percent = re.search(r'\((\d+)%\)', cap)
            months = re.search(WORD_NUMBERS + r'\s*months', cap)
            if times:
                multiple *= Decimal(times.group(1))
            if percent:
                multiple = multiple * Decimal(percent.group(1)) / 100
            if months:
                multiple = multiple * Decimal(months.group(1)) / 12
            add('liability_cap', format(multiple.normalize(), 'f'), cap)
        excluded = sentence(r'(?:not apply|excluded)[^.\n]*indemn|indemn[^.\n]*(?:excluded|not subject)', text)
        indemnity = sentence(r'shall defend', text)
        if excluded:
            add('ip_indemnity', 'uncapped', excluded)
        elif indemnity:
            add('ip_indemnity', 'capped' if cap else 'uncapped', sentence(r'indemnity are subject', text) or indemnity)
    flags = ['PROMPT_INJECTION'] if INJECTION.search(text) else []
    return terms, flags


def run(data):
    contract, positions, requester = agent_module.validate(data)
    terms, flags = read_terms(contract)
    assessed = playbook.assess(contract, positions, terms, flags)
    redlines = [{'topic': d['topic'], 'clause_ref': (d['clause_ref'] or '').split(', ')[0], 'replacement_text': positions[d['topic']]['fallback']}
                for d in assessed['deviations'] if d['severity'] in ('counsel', 'walk_away')]
    output = playbook.review(contract, positions, requester, terms, flags, redlines, [])
    output['baseline'] = 'keyword-checklist'
    return output
