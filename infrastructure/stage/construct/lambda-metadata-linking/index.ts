import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { formatRdsPolicyName } from '@orcabus/platform-cdk-constructs/shared-config/database';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { EventBus, Rule } from 'aws-cdk-lib/aws-events';
import { EVENT_BUS_NAME } from '@orcabus/platform-cdk-constructs/shared-config/event-bridge';

export const REDCAP_TOKEN_PARAMETER_NAME = '/orcabus/case-manager/redcap/redcap-api-token';

type RedCapLambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
};

/**
 * The lambda that triggered by the event bridge rule in interval
 * The setup is triggered daily on roughly every midnight (10.59pm AEST or 11.59pm AEDT)
 */
export class LambdaMetadataEntityLinkConstruct extends Construct {
  readonly lambda: PythonFunction;
  constructor(scope: Construct, id: string, props: RedCapLambdaProps) {
    super(scope, id);

    this.lambda = new PythonFunction(this, 'CaseMetadataLinkLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/metadata_manager_linking.py',
      handler: 'handler',
      timeout: Duration.minutes(15),
      // Not using environment here to prevent overriding from the basicLambdaConfig EnvVar
    });
    this.lambda.role?.addManagedPolicy(
      ManagedPolicy.fromManagedPolicyName(
        this,
        'OrcabusRdsConnectPolicy',
        formatRdsPolicyName('case_manager')
      )
    );

    // Add EventBridge rule to trigger Lambda on MetadataStateChange events from orcabus.metadatamanager
    const redCapLambdaEventTarget = new LambdaFunction(this.lambda);
    new Rule(this, 'RedCapLambdaTriggerOnMetadataStateChange', {
      eventBus: EventBus.fromEventBusName(this, 'OrcaBusEventBus', EVENT_BUS_NAME),
      description:
        'Rule to trigger Lambda on MetadataStateChange events from orcabus.metadatamanager',
      eventPattern: {
        source: ['orcabus.metadatamanager'],
        detailType: ['MetadataStateChange'],
      },
      targets: [redCapLambdaEventTarget],
    });
  }
}
