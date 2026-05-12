import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { formatRdsPolicyName } from '@orcabus/platform-cdk-constructs/shared-config/database';

const REDCAP_TOKEN_PARAMETER_NAME = '/orcabus/case-manager/redcap/redcap-api-token';

type LambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
};

export class LambdaRedCapImportConstruct extends Construct {
  readonly lambda: PythonFunction;
  constructor(scope: Construct, id: string, props: LambdaProps) {
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
  }
}
