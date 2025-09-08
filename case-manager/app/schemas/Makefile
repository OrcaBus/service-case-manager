.PHONY: generate-event-models


generate-event-models:
	datamodel-codegen \
		--input $(shell find ./events -name "*.json") \
		--input-file-type jsonschema \
		--output ./events/models.py

test:
	@check-jsonschema --schemafile ./events/case_external_entity_relationship_created.json ./events/examples/case_entity_relation_create_1.json
