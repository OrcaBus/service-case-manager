import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { Rule, Schedule } from 'aws-cdk-lib/aws-events';
import {
  grantEventBusPublish,
  grantOrcabusServiceAccess,
  grantRdsConnect,
  grantRedcapToken,
} from '../utils';

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
export class LambdaRedCapImportConstruct extends Construct {
  readonly lambda: PythonFunction;
  constructor(scope: Construct, id: string, props: RedCapLambdaProps) {
    super(scope, id);

    this.lambda = new PythonFunction(this, 'RedCapImportLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/redcap_import.py',
      handler: 'handler',
      timeout: Duration.minutes(15),
      // Not using environment here to prevent overriding from the basicLambdaConfig EnvVar
    });
    grantRdsConnect(this.lambda);
    grantRedcapToken(this.lambda);
    grantOrcabusServiceAccess(this.lambda);
    grantEventBusPublish(this.lambda);

    // Add scheduled event to re-sync metadata every midnight
    const redCapLambdaEventTarget = new LambdaFunction(this.lambda);
    new Rule(this, 'RedCapLambdaTriggerScheduledRule', {
      description: 'Scheduled rule to trigger import case from REDCap',
      schedule: Schedule.expression('cron(59 12 * * ? *)'), // 10:59pm AEST or 11:59pm AEDT
      targets: [redCapLambdaEventTarget],
    });
  }
}
