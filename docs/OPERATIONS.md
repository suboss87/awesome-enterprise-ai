# Run one controlled job

The supported operational unit is a read-only decision-support job, owned by one
operator. It accepts an authorized export and produces a proposal for review. It
does not execute a refund, change infrastructure, settle a claim or update an ERP.
The browser is for local exploration, not a hosted application.

## Prepare the host

Use a trusted POSIX host, Python 3.11+ and an immutable reviewed checkout. Run the
workflow checks before processing permitted business data. The operator owns
source authorization, disk encryption, directory access, retention and backup.
Do not run untrusted code under the same OS account. A private run directory is
not tenant isolation, organizational identity or encryption.

Create a private parent directory outside the repository, then use a **new** run
name for each attempt:

```sh
mkdir -m 700 "$HOME/.enterprise-ai-runs"
python3 -m enterprise_ai run customer-resolution \
  --input projects/customer-resolution/examples/input.json \
  --mode replay --responses projects/customer-resolution/examples/responses.json \
  --run-dir "$HOME/.enterprise-ai-runs/support-001"
```

The parent must already exist and be trusted. A symlink or existing run path is
rejected before reading input or invoking the model. The run directory has mode
0700; its JSON artifacts have mode0600. Publication uses same-filesystem POSIX
hard links; storage without hard-link support fails closed. Check support on the
intended volume. Directory permissions do not protect files from administrators.

A successful run contains:

- `result.json`: business output, review requirements and the execution receipt.
- `receipt.json`: execution metadata plus the exact result file's SHA256 and byte
  count. This receipt is published last and marks completed artifact creation.

Stdout contains only status and run ID. Exit2 means failure; it never means the
business request was approved or denied. Input/worker failures leave a sanitized
failure receipt and no result. Artifact-publication failures remove a newly
published result when possible; a storage outage can prevent even a failure
receipt. A missing or mismatched completion receipt is always an incomplete run.
Files are flushed before publication, but this is not a transactional object
store or a guarantee across host/power failure. Operator-accessible receipts are
unsigned and can be changed by that operator.

Before review, compare the receipt's `result_sha256` with the exact result bytes,
confirm run IDs match, and inspect findings and `human_review_required`. Keep the
result immutable. Store human approvals in the organization's normal approval
system against that result hash; a successful execution is not a sign-off.

For live mode, supply an approved input path, select `--mode live`, omit recorded
responses and configure `OPENAI_API_KEY` through the approved secret mechanism.
Provider usage applies. Approval of the provider and data flow is required first.

## Isolated container jobs

The Dockerfile pins the official Python runtime by digest, copies application
files explicitly and runs as a non-root user. It installs no application packages
and exposes no ports. Rebuild and reevaluate when updating the pinned image;
image provenance and vulnerability review remain the deployment owner's duty.

```sh
docker build --tag enterprise-ai:reviewed .
docker run --rm --network=none --read-only --cap-drop=ALL \
  --security-opt=no-new-privileges:true --pids-limit=64 --memory=256m --cpus=1 \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,src=$HOME/.enterprise-ai-runs,dst=/runs" \
  enterprise-ai:reviewed run customer-resolution \
  --input projects/customer-resolution/examples/input.json --mode replay \
  --responses projects/customer-resolution/examples/responses.json \
  --run-dir /runs/container-support-001
```

Use a non-root host user who can access the container engine. The input example
is in the image. Real inputs need a separately authorized **read-only** mount;
never mount the Docker socket or the entire home directory. The writable run
mount must belong to the selected UID/GID. The memory and process limits are exercised by the container checks below. A
passing run verifies the supplied examples at that revision, not capacity for
every business packet. Account for provider latency and use the existing worker deadline.

`--network=none` is appropriate for replay. Live jobs require an administrator's
approved outbound network policy permitting only the intended provider, plus
runtime secret injection. Do not remove network isolation without that policy;
this image does not implement an egress firewall or a secret manager.

To exercise all eleven examples and container boundaries:

```sh
docker build --tag enterprise-ai:ci .
python3 scripts/verify_container.py
```

CI runs the jobs without provider keys or network access, on a read-only root,
with dropped capabilities, no privilege escalation and bounded resources. This
validates packaging and example execution, not live provider access or enterprise
correctness. The image is built for verification; CI does not push an image to a
registry or create an operational deployment.

## Recovery, monitoring and rollback

Alert on a nonzero exit, missing completion receipt, unexpected mode, result hash
mismatch or a blocked business finding. Retain content-free run ID, revision,
duration and status in operational monitoring; never ship source records or
business results into general logs. Restrict access to provider response IDs.

After a timeout or rejected input, preserve the failure receipt and investigate.
There are no automatic retries. A retry needs a new directory and authorization
for any new provider usage. Killing the container or an out-of-memory termination
may prevent a receipt; the scheduler must treat that as failure. These jobs make
no business-system writes, so retrying cannot repeat a refund or system change.

Keep the previous reviewed checkout/image digest and its configuration. Roll
back by running a new job at that revision with a compatible, authorized input;
do not overwrite earlier results or silently migrate frozen evaluation inputs.
A previous revision can have different input contracts. Test rollback and backup
restoration in the target environment before operational acceptance.
