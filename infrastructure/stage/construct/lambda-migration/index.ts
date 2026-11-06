import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { InvocationType, Trigger } from 'aws-cdk-lib/triggers';
import { Duration } from 'aws-cdk-lib';
import { grantRdsConnect } from '../utils';

type LambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
};

export class LambdaMigrationConstruct extends Construct {
  constructor(scope: Construct, id: string, props: LambdaProps) {
    super(scope, id);

    // Lambda to perform migration
    const migrationLambda = new PythonFunction(this, 'MigrationLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/migrate.py',
      handler: 'handler',
      timeout: Duration.minutes(5),
    });
    grantRdsConnect(migrationLambda);

    new Trigger(this, 'MigrationLambdaTrigger', {
      handler: migrationLambda,
      timeout: Duration.minutes(5),
      invocationType: InvocationType.REQUEST_RESPONSE,
    });
  }
}
