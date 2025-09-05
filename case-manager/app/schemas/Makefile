.PHONY: generate-event-models


generate-event-models:
	datamodel-codegen \
		--input $(shell find ./events -name "*.json") \
		--input-file-type jsonschema \
		--output ./events/models.py
