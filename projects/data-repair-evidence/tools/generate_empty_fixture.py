"""Generate a genuine empty GX batch using the existing frozen suite; do not replace prior fixtures."""
import hashlib
import json
import platform
from datetime import datetime, timezone
from importlib.metadata import distributions
from pathlib import Path
import great_expectations as gx
from great_expectations.core import RunIdentifier
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]/'examples/native'
if gx.__version__!='1.8.0':raise SystemExit('Requires existing GX 1.8.0 environment')
context=gx.get_context(mode='ephemeral')
source=context.data_sources.add_pandas(name='synthetic_sales')
asset=source.add_dataframe_asset(name='orders')
batch=asset.add_batch_definition_whole_dataframe('daily_orders')
suite=context.suites.add(gx.ExpectationSuite(**json.loads((ROOT/'suite.json').read_text())))
definition=context.validation_definitions.add(gx.ValidationDefinition(name='orders_quality',data=batch,suite=suite))
baseline_rows={'order_id':[1,None,3],'amount':[100,200,300]}
baseline=definition.run(batch_parameters={'dataframe':pd.DataFrame(baseline_rows)},run_id=RunIdentifier(run_name='empty-baseline-failed',run_time=datetime.now(timezone.utc)))
rows={'order_id':[],'amount':[]}
validation=definition.run(batch_parameters={'dataframe':pd.DataFrame(rows)},run_id=RunIdentifier(run_name='empty',run_time=datetime.now(timezone.utc)))
hashes={}
for name,value in [('empty-rows.json',rows),('empty-gx.json',validation.to_json_dict()),('empty-baseline-rows.json',baseline_rows),('empty-baseline-gx.json',baseline.to_json_dict()),('empty-suite.json',suite.to_json_dict())]:
 path=ROOT/name;path.write_text(json.dumps(value,indent=2)+'\n');hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
hashes['suite.json']=hashlib.sha256((ROOT/'suite.json').read_bytes()).hexdigest()
provenance={'generator':'tools/generate_empty_fixture.py','gx_version':gx.__version__,'python':platform.python_version(),
 'created_at':datetime.now(timezone.utc).isoformat(),'origin':'Actual GX run over original empty dataframe with the previously frozen suite configuration; native IDs assigned by GX. Companion genuine failed baseline uses the same suite. No artifact edits.',
 'artifact_sha256':hashes,'dependencies':sorted(d.metadata['Name']+'=='+d.version for d in distributions()),
 'installation':'Reused isolated environment recorded in provenance.json; no new installation.'}
(ROOT/'empty-provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
