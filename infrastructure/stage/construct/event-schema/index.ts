import { EVENT_SCHEMA_REGISTRY_NAME } from '@orcabus/platform-cdk-constructs/shared-config/event-bridge';
import { CfnSchema } from 'aws-cdk-lib/aws-eventschemas';
import { Construct } from 'constructs';
import { readFileSync } from 'fs';
import { join } from 'path';

export class EventSchemaConstruct extends Construct {
  private readonly SCHEMA_REGISTRY_NAME = 'orcabus.casemanager';

  constructor(scope: Construct, id: string) {
    super(scope, id);

    // case-entity link schema
    this.constructSchema({
      name: `${this.SCHEMA_REGISTRY_NAME}@CaseEntityLinkEvent`,
      schemaPath:
        '../../../../case-manager/app/schemas/events/case_external_entity_relationship_created.json',
      description: 'Schema for linking cases to the external entities',
    });
  }

  private constructSchema = (props: {
    /**
     * The schema name
     */
    name: string;
    /**
     * The path to the schema JSON file relative to this file
     */
    schemaPath: string;
    /**
     * Optional description for the schema
     */
    description?: string;
  }) => {
    return new CfnSchema(this, `EventSchema${props.name}`, {
      registryName: EVENT_SCHEMA_REGISTRY_NAME,
      type: 'JSONSchemaDraft4',
      content: readFileSync(join(__dirname, props.schemaPath), 'utf-8'),
      description: props.description,
      schemaName: props.name,
    });
  };
}
