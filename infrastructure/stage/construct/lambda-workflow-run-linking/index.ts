import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { Rule } from 'aws-cdk-lib/aws-events';
import { grantEventBusPublish, grantOrcabusServiceAccess, grantRdsConnect } from '../utils';

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

type WorkflowRunEntityLinkLambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
};

/**
 * Lambda triggered by EventBridge on WorkflowRunStateChange events
 */
export class LambdaWorkflowRunEntityLinkConstruct extends Construct {
  readonly lambda: PythonFunction;
  constructor(scope: Construct, id: string, props: WorkflowRunEntityLinkLambdaProps) {
    super(scope, id);

    this.lambda = new PythonFunction(this, 'CaseWorkflowRunLinkLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/workflow_run_linking.py',
      handler: 'handler',
      timeout: Duration.minutes(15),
      // Not using environment here to prevent overriding from the basicLambdaConfig EnvVar
    });
    grantRdsConnect(this.lambda);
    grantOrcabusServiceAccess(this.lambda);
    const orcabusEventBus = grantEventBusPublish(this.lambda);

    // Add EventBridge rule to trigger Lambda on WorkflowRunStateChange events to link with cases
    const workflowRunLinkLambdaEventTarget = new LambdaFunction(this.lambda);
    new Rule(this, 'WorkflowRunEntityLinkLambdaRule', {
      eventBus: orcabusEventBus,
      description: 'Rule to trigger Lambda on WorkflowRunStateChange events to link with cases',
      eventPattern: {
        detailType: ['WorkflowRunStateChange'],
        detail: {
          status: ['READY', 'DRAFT'],
          workflow: {
            name: SUPPORTED_WORKFLOWS,
          },
        },
      },
      targets: [workflowRunLinkLambdaEventTarget],
    });
  }
}
