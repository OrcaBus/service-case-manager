.PHONY: generate-event-models


generate-event-models:
	@uv run datamodel-codegen \
		--input ./events/CaseRelationshipStateChange/CaseRelationshipStateChange.schema.json \
		--input-file-type jsonschema \
		--output ./events/CaseRelationshipStateChange/case_relationship_state_change_model.py
	@uv run datamodel-codegen \
		--input ./events/CaseRelationshipUpdate/CaseRelationshipUpdate.schema.json \
		--input-file-type jsonschema \
		--output ./events/CaseRelationshipUpdate/case_relationship_update_model.py


update-workflow-run-update-schema:
	curl -o events/WorkflowRunUpdate/WorkflowRunUpdate.schema.json https://raw.githubusercontent.com/OrcaBus/service-workflow-manager/refs/heads/main/docs/events/WorkflowRunUpdate/WorkflowRunUpdate.schema.json
	@uv run datamodel-codegen \
		--input ./events/WorkflowRunUpdate/WorkflowRunUpdate.schema.json \
		--input-file-type jsonschema \
		--output ./events/WorkflowRunUpdate/workflow_run_update_model.py
test:
	@check-jsonschema --schemafile ./events/CaseRelationshipStateChange.schema.json ./events/examples/case_entity_relation_create_1.json
