import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { Rule } from 'aws-cdk-lib/aws-events';
import { grantEventBusPublish, grantOrcabusServiceAccess, grantRdsConnect } from '../utils';

type SequenceRunStateChangeHandlerProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
};

/**
 * Lambda triggered by EventBridge on SequenceRunStateChange events
 */
export class SequenceRunStateChangeHandler extends Construct {
  readonly lambda: PythonFunction;
  constructor(scope: Construct, id: string, props: SequenceRunStateChangeHandlerProps) {
    super(scope, id);

    this.lambda = new PythonFunction(this, 'SequenceRunStateChangeHandlerLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/sequence_run_state_change.py',
      handler: 'handler',
      timeout: Duration.minutes(15),
      // Not using environment here to prevent overriding from the basicLambdaConfig EnvVar
    });

    grantRdsConnect(this.lambda);
    grantOrcabusServiceAccess(this.lambda);
    const orcabusEventBus = grantEventBusPublish(this.lambda);

    // Add EventBridge rule to trigger Lambda on SequenceRunStateChange events
    const SequenceRunStateChangeHandlerLambda = new LambdaFunction(this.lambda);
    new Rule(this, 'WorkflowRunDraftPublisherTriggerRule', {
      eventBus: orcabusEventBus,
      description:
        'Rule to trigger SequenceRunStateChangeHandlerLambda when sequence status is completed',
      eventPattern: {
        detailType: ['SequenceRunStateChange'],
        detail: {
          status: ['SUCCEEDED'],
        },
      },
      targets: [SequenceRunStateChangeHandlerLambda],
    });
  }
}
