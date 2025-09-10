.PHONY: generate-event-models


generate-event-models:
	@datamodel-codegen \
		--input ./events/CaseRelationshipStateChange.schema.json \
		--input-file-type jsonschema \
		--output ./events/case_srelationship_state_change_model.py
	@datamodel-codegen \
		--input ./events/CaseRelationshipUpdate.schema.json \
		--input-file-type jsonschema \
		--output ./events/case_relationship_update_model.py

test:
	@check-jsonschema --schemafile ./events/CaseRelationshipStateChange.schema.json ./events/examples/case_entity_relation_create_1.json
