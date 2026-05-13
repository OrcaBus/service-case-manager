import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { IManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { IVpc } from 'aws-cdk-lib/aws-ec2';
import { Duration } from 'aws-cdk-lib';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';

type LambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
  /**
   * Managed policy granting `rds-db:connect` on the RDS cluster
   */
  rdsConnectPolicy: IManagedPolicy;
  /**
   * VPC used for Custom Provider Function
   */
  vpc: IVpc;
};

export class LambdaCaseFinderConstruct extends Construct {
  readonly lambda: PythonFunction;
  constructor(scope: Construct, id: string, props: LambdaProps) {
    super(scope, id);

    const roOrcabusDbCreds = Secret.fromSecretNameV2(this, 'RoOrcabusDbCreds', 'orcabus/ro-user');

    this.lambda = new PythonFunction(this, 'CaseFinderLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/case_finder.py',
      handler: 'handler',
      timeout: Duration.minutes(15),
      // Not using environment here to prevent overriding from the basicLambdaConfig EnvVar
    });
    this.lambda.addEnvironment('ORCABUS_RO_USER_SECRET_ARN', roOrcabusDbCreds.secretArn);

    this.lambda.role?.addManagedPolicy(props.rdsConnectPolicy);
    roOrcabusDbCreds.grantRead(this.lambda);
  }
}
