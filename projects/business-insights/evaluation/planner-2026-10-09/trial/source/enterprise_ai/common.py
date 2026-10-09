"""Shared input contracts, structured model interface, and evidence checks."""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import json
import math


class InputError(ValueError):
    pass


def loads(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise InputError('Duplicate JSON key')
            result[key] = value
        return result
    def finite_float(raw_number):
        value=float(raw_number)
        if not math.isfinite(value):
            raise InputError('Non-finite number')
        return value
    try:
        return json.loads(raw, object_pairs_hook=pairs, parse_float=finite_float,
                          parse_constant=lambda _: (_ for _ in ()).throw(InputError('Non-finite number')))
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise InputError('Invalid JSON: duplicate keys and non-finite numbers are forbidden') from exc


def obj(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= value.keys() or value.keys()-set(required)-set(optional):
        raise InputError('Expected fields: '+', '.join(required)+'; optional: '+', '.join(optional))
    return value


def text(value, name='text', limit=10000):
    if not isinstance(value, str) or not value.strip() or len(value)>limit:
        raise InputError(f'{name} must be nonempty text (maximum {limit} characters)')
    try:
        value.encode('utf-8')
    except UnicodeError as exc:
        raise InputError('Invalid Unicode') from exc
    if any(ord(c)<32 and c not in '\n\t\r' for c in value):
        raise InputError('Control characters are forbidden')
    return value


def integer(value, name='integer', minimum=0, maximum=1000000000):
    if type(value) is not int or not minimum<=value<=maximum:
        raise InputError(f'{name} must be an integer between {minimum} and {maximum}')
    return value


def number(value, name='number', minimum=-1e12, maximum=1e12):
    if type(value) not in (int,float) or not minimum<=value<=maximum or not math.isfinite(value):
        raise InputError(f'Invalid {name}')
    return value


def money(value):
    text(value, 'decimal amount', 32)
    import re
    if not re.fullmatch(r'-?\d{1,12}(\.\d{1,2})?',value):
        raise InputError('Money requires a plain decimal string with at most two decimals')
    return Decimal(value)


def day(value):
    text(value, 'ISO date',10)
    try:
        parsed=date.fromisoformat(value)
    except ValueError as exc:
        raise InputError('Expected YYYY-MM-DD') from exc
    if parsed.isoformat()!=value:
        raise InputError('Expected YYYY-MM-DD')
    return parsed


def rows(value, name='records', maximum=500, minimum=0):
    if not isinstance(value,list) or not minimum<=len(value)<=maximum:
        raise InputError(f'{name} requires {minimum} to {maximum} records')
    return value


def unique(records, key='id'):
    ids=[text(r.get(key),key,128) for r in records if isinstance(r,dict)]
    if len(ids)!=len(records) or len(set(ids))!=len(ids):
        raise InputError('Records require unique nonempty '+key)
    return {r[key]:r for r in records}


def object_schema(properties):
    return {'type':'object','properties':properties,'required':list(properties),'additionalProperties':False}


def array_schema(items):
    return {'type':'array','items':items}


def string_schema(enum=None):
    result={'type':'string'}
    if enum is not None:
        result['enum']=list(enum)
    return result


def validate_schema(value, schema, path='result'):
    kind=schema['type']
    if kind=='object':
        obj(value,schema['required'])
        for key,spec in schema['properties'].items():
            validate_schema(value[key],spec,path+'.'+key)
    elif kind=='array':
        rows(value,path,maximum=1000)
        for item in value:
            validate_schema(item,schema['items'],path+'[]')
    elif kind=='string':
        if not isinstance(value,str) or len(value)>20000:
            raise InputError('Invalid '+path)
        if 'enum' in schema and value not in schema['enum']:
            raise InputError('Unsupported value for '+path)
    elif kind=='integer':
        integer(value,path,minimum=schema.get('minimum',-1000000000),maximum=schema.get('maximum',1000000000))
    elif kind=='number':
        number(value,path,minimum=schema.get('minimum',-1e12),maximum=schema.get('maximum',1e12))
    elif kind=='boolean':
        if type(value) is not bool:
            raise InputError('Expected boolean '+path)
    else:
        raise InputError('Unsupported schema type')


def evidence(items, sources):
    """Validate exact quotations; entailment still requires evaluation and review."""
    rows(items,'evidence',100)
    seen=set()
    for item in items:
        obj(item,['source_id','quote'])
        sid=text(item['source_id'],'source_id',128)
        quote=text(item['quote'],'quote',20000)
        if sid not in sources or quote not in sources[sid]:
            raise InputError('Model citation is not an exact source quotation')
        if (sid,quote) in seen:
            raise InputError('Duplicate evidence quotation')
        seen.add((sid,quote))
    return items


EVIDENCE_SCHEMA=array_schema(object_schema({'source_id':string_schema(),'quote':string_schema()}))


def finding(code, severity, title, detail, evidence_ids=()):
    if severity not in ('info','review','urgent'):
        raise InputError('Invalid finding severity')
    return {'code':code,'severity':severity,'title':title,'detail':detail,'evidence_ids':list(evidence_ids)}


def result(project, summary, metrics, findings, actions=(), **extra):
    return {'project':project,'summary':summary,'metrics':metrics,'findings':list(findings),
            'actions':list(actions),'human_review_required':True,**extra}


class ReplayAI:
    """Explicit offline replay. Never presented as actual model inference."""
    def __init__(self,responses):
        self.responses=list(responses)
        self.calls=[]

    def ask(self,instructions,data,schema):
        if not self.responses:
            raise InputError('Replay has no response for this model call')
        value=self.responses.pop(0)
        validate_schema(value,schema)
        self.calls.append({'mode':'replay','model':None})
        return value
