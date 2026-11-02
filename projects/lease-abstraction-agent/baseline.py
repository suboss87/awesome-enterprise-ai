"""Rules-only baseline in the style of a regex abstraction template.

A lease administration team without a model writes one regular expression per field for its
own lease template: the parties before ("Landlord") and ("Tenant"), the first area in square
feet, the date after "commencing on" or "Commencement Date:", the date after "expir",
"(N) months" in the term sentence, "monthly Base Rent of $X", "Annual Base Rent ... $X" or rent table
rows (not rent per rentable square foot), the
percentage after "increases by", the three renewal phrasings in use, the termination date and fee,
the security deposit, the CAM type and cap, the holdover percentage or multiple, the
consent standard, and a short blocklist for instructions aimed at software. It abstracts the
original lease and updates the abstract from the most recent document in the package only,
as a team does when it files the newest amendment, letter or estoppel. Each hit is quoted
verbatim (the whole line) and the statements go through the same `abstraction.py` rules as
the agent, so the comparison isolates the reading step.
"""
import calendar
import importlib.util
import re
from datetime import datetime
from pathlib import Path

_here = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('lease_abstraction_rules_b', _here/'abstraction.py')
abstraction = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(abstraction)
_aspec = importlib.util.spec_from_file_location('lease_agent_b', _here/'agent.py')
agent_module = importlib.util.module_from_spec(_aspec)
_aspec.loader.exec_module(agent_module)

MONTHS = '|'.join(calendar.month_name[1:])
DATE = rf'(?:(?:{MONTHS}) \d{{1,2}}, \d{{4}}|\d{{1,2}} (?:{MONTHS}) \d{{4}})'
MONEY = r'\$([\d,]+\.\d\d)'
INJECTION = re.compile(r'automated (?:abstraction )?system|AI abstraction tool|ignore the amendments', re.I)


def iso(text):
    for fmt in ('%B %d, %Y', '%d %B %Y'):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def amount(text):
    return text.replace(',', '')


def read_line(line, kind):
    """Statements (field, value) that the template finds in one line."""
    found = []

    def hit(pattern, flags=0):
        return re.search(pattern, line, flags)

    if m := hit(r'between (.+?) \("Landlord"\)') or hit(r'^Landlord: (.+)$'):
        found.append(('landlord', m.group(1)))
    if m := hit(r'\("Landlord"\) and (.+?) \("Tenant"\)') or hit(r'^Tenant: (.+)$'):
        found.append(('tenant', m.group(1)))
    if m := hit(r'leases to Tenant (.+?) \(the "Premises"\)') or hit(r'^Premises: (.+)$'):
        found.append(('premises', m.group(1).replace(' of ', ', ', 1)))
    if m := hit(r'([\d,]+) (?:rentable )?square feet'):
        found.append(('rentable_area', f'{amount(m.group(1))} sq ft'))
    elif m := hit(r'([\d,]+) square met(?:er|re)s'):
        found.append(('rentable_area', f'{amount(m.group(1))} sq m'))
    if 'Commencement Date' in line:
        if m := hit(rf'[Cc]ommenc\w*[^.]*?({DATE})'):
            found.append(('commencement_date', iso(m.group(1))))
        elif 'deliver' in line:
            found.append(('commencement_date', 'on_delivery'))
    if m := hit(rf'(?:expir\w*|extended to)[^.]*?({DATE})', re.I):
        found.append(('expiration_date', iso(m.group(1))))
    if (line.startswith('Term:') or re.search(r'commenc', line, re.I)) and (m := hit(r'\((\d+)\) months')):
        found.append(('term_months', m.group(1)))
    if m := hit(rf'monthly Base Rent of {MONEY}') or hit(rf'^Monthly Base Rent \(first Lease Year\): {MONEY}'):
        found.append(('base_rent', f'{amount(m.group(1))} monthly'))
    elif m := hit(rf'^Annual Base Rent[^$]*{MONEY}') or hit(rf'Annual Base Rent for the first Lease Year is {MONEY}'):
        found.append(('base_rent', f'{amount(m.group(1))} annual'))
    if m := hit(rf'^\| ({DATE}) to {DATE} \| {MONEY} per month \|'):
        found.append(('rent_step', f'{iso(m.group(1))}: {amount(m.group(2))} monthly'))
    if m := hit(rf'^\| Months (\d+)-\d+ \| {MONEY} per month \|'):
        found.append(('rent_step', f'month {m.group(1)}: {amount(m.group(2))} monthly'))
    if m := hit(r'increases by [^()]*\((\d+(?:\.\d+)?)%\)'):
        found.append(('escalation', f'fixed_pct {m.group(1)} every 12 months'))
    elif m := hit(rf'increases by {MONEY}'):
        found.append(('escalation', f'fixed_amount {amount(m.group(1))} every 12 months'))
    elif 'Consumer Price Index' in line:
        found.append(('escalation', 'cpi'))
    if re.search(r'option to extend|renew this Lease|extend the Term', line):
        count, term = hit(r'\((\d+)\) (?:option|additional|time)'), hit(r'(?:terms? of|for) [^()]*\((\d+)\) (years|months)')
        window = hit(r'not less than [^()]*\((\d+)\) (months|days) and not more than [^()]*\((\d+)\) (?:months|days)')
        reverse = hit(r'no earlier than [^()]*\((\d+)\) (days|months) and no later than [^()]*\((\d+)\) (?:days|months)')
        least = hit(r'at least [^()]*\((\d+)\) (days|months)')
        basis = 'fmv' if 'Market' in line else 'fixed'
        notice = (f'{window.group(1)} to {window.group(3)} {window.group(2)}' if window else
                  f'{reverse.group(3)} to {reverse.group(1)} {reverse.group(2)}' if reverse else
                  f'at least {least.group(1)} {least.group(2)}' if least else None)
        if count and term and notice:
            found.append(('renewal_option', f'{count.group(1)} x {term.group(1)} {term.group(2)}, notice {notice}, rent {basis}'))
    if (m := hit(rf'terminate this Lease effective as of ({DATE})')) and (n := hit(r"\((\d+)\) (days|months)'")) and (fee := hit(rf'fee of {MONEY}')):
        found.append(('termination_option', f'{iso(m.group(1))}, notice {n.group(1)} {n.group(2)}, fee {amount(fee.group(1))}'))
    if m := hit(rf'{MONEY} with Landlord as a security deposit') or hit(rf'^Security Deposit: {MONEY}') or hit(rf'security deposit of {MONEY}'):
        found.append(('security_deposit', amount(m.group(1))))
    if 'full service gross' in line:
        found.append(('cam', 'gross'))
    elif 'net lease' in line:
        cap = hit(r'more than [^()]*\((\d+)%\)')
        found.append(('cam', f'net cap {cap.group(1)}' if cap else 'net'))
    elif 'Base Year' in line:
        cap = hit(r'capped at [^()]*\((\d+)%\)')
        found.append(('cam', f'modified_gross cap {cap.group(1)}' if cap else 'modified_gross'))
    if 'holdover' in line:
        if m := hit(r'\((\d+)%\)'):
            found.append(('holdover', f'{m.group(1)}%'))
        elif m := hit(r'\((\d(?:\.\d)?)\) times'):
            found.append(('holdover', f'{m.group(1)}x'))
    if 'assign' in line and 'consent' in line:
        found.append(('assignment_consent', 'not_unreasonably_withheld' if 'unreasonably' in line else 'sole_discretion'))
    if m := hit(rf'(?:current monthly Base Rent is|payable as of the Commencement Date is) {MONEY}'):
        found.append(('current_rent', amount(m.group(1))))
    return [(f, v) for f, v in found if v and kind in abstraction.FIELD_KINDS.get(f, abstraction.KINDS)]


def read_document(doc, single=False):
    statements, seen = [], set()
    for line in doc['text'].splitlines():
        for field, value in read_line(line.strip(), doc['kind']):
            if single and field in seen and field != 'rent_step':
                continue
            seen.add(field)
            statements.append({'document_id': doc['id'], 'field': field, 'value': value, 'quote': line.strip()})
    return statements


def run(data):
    lease, _ = agent_module.validate(data)
    base = [d for d in lease['documents'] if d['kind'] == 'lease']
    others = sorted((d for d in lease['documents'] if d['kind'] != 'lease'), key=lambda d: d['effective_date'])
    read = base + others[-1:]
    statements = [s for doc in read for s in read_document(doc, single=True)]
    flags = ['PROMPT_INJECTION'] if any(INJECTION.search(d['text']) for d in read) else []
    output = abstraction.build_output(data, statements, flags, [], [])
    output['baseline'] = 'regex-template'
    return output
