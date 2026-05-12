import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { formatRdsPolicyName } from '@orcabus/platform-cdk-constructs/shared-config/database';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';
import { Rule, Schedule } from 'aws-cdk-lib/aws-events';

const REDCAP_TOKEN_PARAMETER_NAME = '/orcabus/case-manager/redcap/redcap-api-token';

type RedCapLambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
  /**
   * Trigger daily sync every night
   */
  isDailySync?: boolean;
};

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
    this.lambda.role?.addManagedPolicy(
      ManagedPolicy.fromManagedPolicyName(
        this,
        'OrcabusRdsConnectPolicy',
        formatRdsPolicyName('case_manager')
      )
    );

    this.lambda.addEnvironment('REDCAP_TOKEN_PARAMETER_NAME', REDCAP_TOKEN_PARAMETER_NAME);
    const redcapTokenSSM = StringParameter.fromSecureStringParameterAttributes(
      this,
      'RedcapTokenSSM',
      { parameterName: REDCAP_TOKEN_PARAMETER_NAME }
    );
    redcapTokenSSM.grantRead(this.lambda);

    if (props.isDailySync) {
      // Add scheduled event to re-sync metadata every midnight
      const redCapLambdaEventTarget = new LambdaFunction(this.lambda);
      new Rule(this, 'RedCapLambdaTriggerScheduledRule', {
        description: 'Scheduled rule to trigger import case from REDCap',
        schedule: Schedule.expression('cron(0 13 * * ? *)'), // 11pm AEST or 12am AEDT
        targets: [redCapLambdaEventTarget],
      });
    }
  }
}
