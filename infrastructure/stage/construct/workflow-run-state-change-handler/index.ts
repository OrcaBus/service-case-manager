import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { formatRdsPolicyName } from '@orcabus/platform-cdk-constructs/shared-config/database';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { EventBus, Match, Rule } from 'aws-cdk-lib/aws-events';
import { EVENT_BUS_NAME } from '@orcabus/platform-cdk-constructs/shared-config/event-bridge';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { JWT_SECRET_NAME } from '@orcabus/platform-cdk-constructs/shared-config/secrets';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';

const WGS_WORKFLOW = ['sash', 'tumor-normal', 'dragen-wgts-dna', 'oncoanalyser-wgts-dna'];
const WTS_WORKFLOW = ['wts', 'dragen-wgts-rna', 'oncoanalyser-wgts-rna'];
const WGS_WTS_WORKFLOW = ['oncoanalyser-wgts-dna-rna', 'arriba-wgts-rna', 'rnasum'];
const CTTSO_WORKFLOW = ['dragen-tso500-ctdna', 'cttsov2', 'pieriandx-tso500-ctdna'];
const SUPPORTED_WORKFLOWS = [
  ...WGS_WORKFLOW,
  ...WTS_WORKFLOW,
  ...WGS_WTS_WORKFLOW,
  ...CTTSO_WORKFLOW,
];

type WorkflowRunStateChangeHandlerProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
};

/**
 * Lambda triggered by EventBridge on WorkflowRunStateChange events.
 *
 * Unlike the linking handler (which only fires on READY/DRAFT), this handler is
 * intentionally triggered on WorkflowRunStateChange events regardless of status.
 * It re-evaluates ("reconciles") the bioinformatics state of every case linked to
 * the workflow run on each event, so a transition is never permanently missed even
 * if an event arrives before the run has been linked to a case.
 */
export class WorkflowRunStateChangeHandler extends Construct {
  readonly lambda: PythonFunction;
  constructor(scope: Construct, id: string, props: WorkflowRunStateChangeHandlerProps) {
    super(scope, id);

    this.lambda = new PythonFunction(this, 'WorkflowRunStateChangeHandlerLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/workflow_run_state_change.py',
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

    // pass the domain name for other services
    const hostedZoneName = StringParameter.valueFromLookup(this, '/hosted_zone/umccr/name');
    this.lambda.addEnvironment('HOSTED_ZONE_NAME', hostedZoneName);

    // allow lambda to retrieve the service user JWT
    const serviceUserJwtSecret = Secret.fromSecretNameV2(
      this,
      'serviceUserJwtSecret',
      JWT_SECRET_NAME
    );
    this.lambda.addEnvironment('ORCABUS_SERVICE_JWT_SECRET_ARN', serviceUserJwtSecret.secretArn);
    serviceUserJwtSecret.grantRead(this.lambda);

    const orcabusEventBus = EventBus.fromEventBusName(this, 'EventBus', EVENT_BUS_NAME);
    orcabusEventBus.grantPutEventsTo(this.lambda);
    this.lambda.addEnvironment('EVENT_BUS_NAME', EVENT_BUS_NAME);

    // Add EventBridge rule to trigger Lambda on WorkflowRunStateChange events.
    // No status filter: the handler accepts every status and reconciles the case's
    // bioinformatics state on each event.
    const workflowRunStateChangeLambdaTarget = new LambdaFunction(this.lambda);
    new Rule(this, 'WorkflowRunStateChangeHandlerRule', {
      eventBus: orcabusEventBus,
      description:
        'Rule to trigger the bioinformatics state update Lambda on all WorkflowRunStateChange events',
      eventPattern: {
        detailType: ['WorkflowRunStateChange'],
        detail: {
          status: Match.anythingBut('DRAFT'),
          workflow: {
            name: SUPPORTED_WORKFLOWS,
          },
        },
      },
      targets: [workflowRunStateChangeLambdaTarget],
    });
  }
}
