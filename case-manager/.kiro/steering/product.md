# Product

Case Manager is an OrcaBus microservice (UMCCR). Its job is **orchestration**: it
groups entities from across the OrcaBus platform under a single **case** so other
services know what belongs together and what to run.

## What a case is

A case is a grouping identified by its own orcabus_id (prefix `cas`). It links to
entities that live in — and are owned by — other OrcaBus microservices, referenced
by their orcabus_id: libraries, samples, sequence runs, workflow runs, files, etc.

A case carries:

- **Orchestration attributes** other services depend on to do their work (e.g.
  the case `type`, which drives what workflow should run).
- **Convenience attributes** kept for display/cross-referencing only. These are
  not core to orchestration and should ideally shrink over time — do not build new
  behaviour that depends on them.

Cases are currently created by syncing from an external system (REDCap), and the
design should also accommodate manual creation in future. Anything sourced from
REDCap is treated as a clinical case.

## Linking model

Links are generic. A case links to an `ExternalEntity`, which records the entity's
`orcabus_id`, owning `service_name` (e.g. `metadata`, `sequence`, `workflow`), a
`type` (e.g. `library`, `sample`, `sequence`), and a human-friendly `alias`. The
case manager does not own these entities — it only records the relationship. This
is why there is no fixed, hard-coded entity set: any entity addressable by
orcabus_id can be linked.

- **Automatic linking:** EventBridge rules drive Lambda handlers (`handler/`) that
  listen for platform events and link the appropriate metadata / sequence run /
  workflow run entities to a case.
- **Manual correction:** the REST API is used to link/unlink entities when the
  automatic linking is wrong or incomplete.

## Status lifecycle

Every case has a status (see `CaseStatus` in `app/models/state.py`), moving through
intake → library prep → sequencing → bioinformatics → curation → reporting →
terminal states. Status changes are recorded as append-only `State` records.

`LOCKED`, `COMPLETED`, and `ARCHIVED` are blocking: while a case is in one of these,
new external-entity links are refused at the model level so the audit trail can't be
silently corrupted. To link again, transition the case out of the blocking state.

## Events

The service publishes to EventBridge so other services can react (exact detail-type
strings, verified against the generated event models):

- `CaseRelationshipStateChange` — emitted when a case↔entity link is created or
  removed (see `app/service/case.py`).
- `CaseStateChange` — emitted when the case's own data is created or updated (see
  `app/service/redcap_import.py`).

Events are emitted only after the DB transaction commits (`transaction.on_commit`).

## Integration surface

- A REST API (OpenAPI/Swagger at `/schema/swagger-ui/`) lets other services query
  live case information and link/unlink entities.
- REDCap sync runs on a schedule (nightly) via the REDCap import handler, picking up
  the window since the last successful sync; it can also be triggered on demand
  through the API. Note: the schedule itself is configured outside this repo (in the
  platform's infrastructure that invokes the Lambda).
- All meaningful mutations are audited (acting user + change reason) via
  django-simple-history.
