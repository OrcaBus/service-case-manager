import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { Rule } from 'aws-cdk-lib/aws-events';
import { grantEventBusPublish, grantOrcabusServiceAccess, grantRdsConnect } from '../utils';

type SequenceRunEntityLinkLambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
};

/**
 * Lambda triggered by EventBridge on SequenceRunStateChange events
 */
export class LambdaSequenceRunEntityLinkConstruct extends Construct {
  readonly lambda: PythonFunction;
  constructor(scope: Construct, id: string, props: SequenceRunEntityLinkLambdaProps) {
    super(scope, id);

    this.lambda = new PythonFunction(this, 'CaseSequenceRunLinkLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/sequence_run_linking.py',
      handler: 'handler',
      timeout: Duration.minutes(15),
      // Not using environment here to prevent overriding from the basicLambdaConfig EnvVar
    });
    grantRdsConnect(this.lambda);
    grantOrcabusServiceAccess(this.lambda);
    const orcabusEventBus = grantEventBusPublish(this.lambda);

    // Add EventBridge rule to trigger Lambda on SequenceRunStateChange events to link with cases
    const sequenceRunLinkLambdaEventTarget = new LambdaFunction(this.lambda);
    new Rule(this, 'SequenceRunLibraryEntityLinkLambdaRule', {
      eventBus: orcabusEventBus,
      description:
        'Rule to trigger Lambda on SequenceRunLibraryLinkingChange events to link with cases',
      eventPattern: {
        detailType: ['SequenceRunLibraryLinkingChange'],
      },
      targets: [sequenceRunLinkLambdaEventTarget],
    });
  }
}
