FROM python:3.11.17-slim-bookworm@sha256:0a310eeecf4e1f5a0743f9a6520c90c88d089c903ca5fd283f501e3a805f5f89
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY enterprise_ai/ enterprise_ai/
COPY projects/customer-resolution/workflow.py projects/customer-resolution/workflow.py
COPY projects/incident-operations/workflow.py projects/incident-operations/workflow.py
COPY projects/exposure-review/workflow.py projects/exposure-review/workflow.py
COPY projects/business-insights/workflow.py projects/business-insights/workflow.py
COPY projects/inventory-decisions/workflow.py projects/inventory-decisions/workflow.py
COPY projects/asset-operations/workflow.py projects/asset-operations/workflow.py
COPY projects/claims-intake/workflow.py projects/claims-intake/workflow.py
COPY projects/proposal-operations/workflow.py projects/proposal-operations/workflow.py
COPY projects/account-intelligence/workflow.py projects/account-intelligence/workflow.py
COPY projects/workforce-onboarding/workflow.py projects/workforce-onboarding/workflow.py
COPY projects/data-repair-evidence/workflow.py projects/data-repair-evidence/workflow.py
COPY LICENSE LICENSE
USER 65532:65532
ENTRYPOINT ["python3", "-m", "enterprise_ai"]
CMD ["list"]
