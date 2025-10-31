import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { IDatabaseCluster } from 'aws-cdk-lib/aws-rds';
import { IVpc } from 'aws-cdk-lib/aws-ec2';
import { Duration } from 'aws-cdk-lib';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';

type LambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
  /**
   * The db cluster to where the lambda authorize to connect
   */
  databaseCluster: IDatabaseCluster;
  /**
   * The database name that the lambda will use
   */
  databaseName: string;
  /**
   * VPC used for Custom Provider Function
   */
  vpc: IVpc;
};

export class LambdaCaseFinderConstruct extends Construct {
  constructor(scope: Construct, id: string, props: LambdaProps) {
    super(scope, id);

    const domainName = StringParameter.valueForStringParameter(this, '/hosted_zone/umccr/name');
    const jwtSecret = Secret.fromSecretNameV2(
      this,
      'JwtSecretService',
      'orcabus/token-service-jwt'
    );

    const caseFinderLambda = new PythonFunction(this, 'CaseFinderLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/case_finder.py',
      handler: 'handler',
      timeout: Duration.minutes(15),
      environment: {
        DOMAIN_NAME: domainName,
        ORCABUS_SERVICE_JWT_SECRET_ARN: jwtSecret.secretArn,
      },
    });
    props.databaseCluster.grantConnect(caseFinderLambda, props.databaseName);
    jwtSecret.grantRead(caseFinderLambda);
  }
}
