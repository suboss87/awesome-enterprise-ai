"""Development-only generator: run with pinned GX 1.8.0, never at workflow runtime."""
import hashlib
import json
from pathlib import Path
import platform
from importlib.metadata import distributions
from datetime import datetime, timezone
import great_expectations as gx
from great_expectations.core import RunIdentifier
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
if gx.__version__ != '1.8.0': raise SystemExit('Fixture generator requires GX 1.8.0')
context=gx.get_context(mode='ephemeral')
source=context.data_sources.add_pandas(name='synthetic_sales')
asset=source.add_dataframe_asset(name='orders')
batchdef=asset.add_batch_definition_whole_dataframe('daily_orders')
suite=gx.ExpectationSuite(name='order_contract')
suite.add_expectation(gx.expectations.ExpectColumnValuesToNotBeNull(column='order_id'))
suite.add_expectation(gx.expectations.ExpectColumnValuesToBeBetween(column='amount', min_value=0, max_value=10000))
suite=context.suites.add(suite)
definition=context.validation_definitions.add(gx.ValidationDefinition(name='orders_quality',data=batchdef,suite=suite))
def write(name,data):
 path=ROOT/'examples/native'/name
 path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+'\n')
 return hashlib.sha256(path.read_bytes()).hexdigest()
hashes={}
for label, ids in [('failed',[1,None,3]),('repaired',[1,2,3])]:
 rows={'order_id':ids,'amount':[100,200,300]}
 hashes[label+'-rows.json']=write(label+'-rows.json',rows)
 result=definition.run(batch_parameters={'dataframe':pd.DataFrame(rows)},run_id=RunIdentifier(run_name=label,run_time=datetime.now(timezone.utc)))
 hashes[label+'-gx.json']=write(label+'-gx.json',result.to_json_dict())
hashes['suite.json']=write('suite.json',suite.to_json_dict())
write('provenance.json',{'generator':'tools/generate_gx_fixtures.py','gx_version':gx.__version__,
 'python':platform.python_version(),'created_at':datetime.now(timezone.utc).isoformat(),
 'origin':'Actual local GX runs over independently authored synthetic rows; no external customer data.',
 'pypi_release_uploaded_at':'2025-10-23T20:16:19.780175Z','dependency_exclude_newer':'2026-09-18T00:00:00Z',
 'artifact_sha256':hashes,'dependencies':sorted(d.metadata['Name']+'=='+d.version for d in distributions())})
