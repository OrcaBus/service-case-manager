# WorkflowRunUpdate Event Schema

## Overview

This directory contains the WorkflowRunUpdate event schema imported from the [OrcaBus Workflow Manager service](https://github.com/OrcaBus/service-workflow-manager).

## Source

The schema is sourced from:
- **Repository**: https://github.com/OrcaBus/service-workflow-manager
- **Path**: `docs/events/WorkflowRunUpdate/WorkflowRunUpdate.schema.json`
- **Branch**: `main`

## Schema Details

The WorkflowRunUpdate schema defines EventBridge events that represent workflow execution updates. Key fields include:

- **orcabusId**: Workflow run OrcaBus identifier
- **portalRunId**: Unique portal run identifier (format: YYYYMMDD{uuid8})
- **workflowRunName**: Descriptive workflow run name
- **workflow**: Workflow metadata (name, version, execution engine, etc.)
- **libraries**: Array of library objects with readset details
- **status**: Current workflow run status (e.g., DRAFT, RUNNING, SUCCEEDED, FAILED)

### Field Naming Convention

The schema uses **camelCase** field names (e.g., `orcabusId`, `portalRunId`, `workflowRunName`) which matches EventBridge conventions.

## Files

- `WorkflowRunUpdate.schema.json` - JSON Schema definition
- `workflow_run_update_model.py` - Generated Pydantic models (auto-generated, do not edit manually)
- `README.md` - This documentation file

## Updating the Schema

To update the schema to the latest version from the workflow-manager repository:

```bash
# From the case-manager root directory
cd app/schemas/events/WorkflowRunUpdate

# Download the latest schema
curl -L -o WorkflowRunUpdate.schema.json \
  https://raw.githubusercontent.com/OrcaBus/service-workflow-manager/main/docs/events/WorkflowRunUpdate/WorkflowRunUpdate.schema.json

# Regenerate Python models
cd ../..  # Back to app/schemas
make generate-event-models
```

Alternatively, if the workflow-manager repository structure changes, you can pull specific commits:

```bash
# Pull a specific version (from git root of service-case-manager)
# Note: This requires running from the repository root, not the case-manager subdirectory
git subtree pull --prefix=case-manager/app/schemas/events/WorkflowRunUpdate/upstream \
  https://github.com/OrcaBus/service-workflow-manager.git <commit-sha> --squash
```

## Python Model Generation

The Python Pydantic models are generated automatically using `datamodel-codegen`:

```bash
# From app/schemas directory
make generate-event-models
```

This command:
1. Reads the JSON Schema file
2. Generates Pydantic models with type hints
3. Outputs to `workflow_run_update_model.py`

**Important**: Do not manually edit `workflow_run_update_model.py` - it will be overwritten on the next generation.

## Usage

Import the generated models in your code:

```python
from app.schemas.events.WorkflowRunUpdate.workflow_run_update_model import (
    WorkflowRunUpdate,
    Library,
    Readset,
    Workflow,
    AnalysisRun,
    Payload
)

# Use the models for validation and serialization
workflow_run_data = WorkflowRunUpdate(
    portalRunId="20240120abc12345",
    workflowRunName="umccr--automated--dragen-tso500-ctdna--4-3-6--20240120abc12345",
    workflow=Workflow(orcabusId="wfl.abc123", name="dragen-tso500-ctdna"),
    libraries=[...],
    status="DRAFT"
)
```

## Version History

- **Initial Import**: 2024-01-20 - Imported schema from workflow-manager main branch
  - Source commit: latest as of import date
  - Schema version: EventBridge draft-04 format

## Notes

- This schema is maintained by the Workflow Manager team
- Any changes to field names, types, or required fields should be coordinated with the workflow-manager service
- The schema uses draft-04 JSON Schema specification
- Generated Python models use Pydantic v2.x for validation
