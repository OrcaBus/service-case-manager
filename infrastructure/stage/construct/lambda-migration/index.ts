import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { InvocationType, Trigger } from 'aws-cdk-lib/triggers';
import { Duration } from 'aws-cdk-lib';
import { formatRdsPolicyName } from '@orcabus/platform-cdk-constructs/shared-config/database';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';

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
    migrationLambda.role?.addManagedPolicy(
      ManagedPolicy.fromManagedPolicyName(
        this,
        'OrcabusRdsConnectPolicy',
        formatRdsPolicyName('case_manager')
      )
    );

    new Trigger(this, 'MigrationLambdaTrigger', {
      handler: migrationLambda,
      timeout: Duration.minutes(5),
      invocationType: InvocationType.REQUEST_RESPONSE,
    });
  }
}
