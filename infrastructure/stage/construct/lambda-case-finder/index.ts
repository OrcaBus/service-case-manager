import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { IDatabaseCluster } from 'aws-cdk-lib/aws-rds';
import { IVpc } from 'aws-cdk-lib/aws-ec2';
import { Duration } from 'aws-cdk-lib';
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

    const roOrcabusDbCreds = Secret.fromSecretNameV2(this, 'RoOrcabusDbCreds', 'orcabus/ro-user');

    const caseFinderLambda = new PythonFunction(this, 'CaseFinderLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/case_finder.py',
      handler: 'handler',
      timeout: Duration.minutes(15),
      // Not using environment here to prevent overriding from the basicLambdaConfig EnvVar
    });
    caseFinderLambda.addEnvironment('ORCABUS_RO_USER_SECRET_ARN', roOrcabusDbCreds.secretArn);

    props.databaseCluster.grantConnect(caseFinderLambda, props.databaseName);
    roOrcabusDbCreds.grantRead(caseFinderLambda);
  }
}
