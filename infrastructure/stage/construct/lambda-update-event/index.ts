import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { IManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { Duration } from 'aws-cdk-lib';
import { EventBus, Rule } from 'aws-cdk-lib/aws-events';
import { EVENT_BUS_NAME } from '@orcabus/platform-cdk-constructs/shared-config/event-bridge';
import { LambdaFunction } from 'aws-cdk-lib/aws-events-targets';

type LambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
  /**
   * Managed policy granting `rds-db:connect` on the RDS cluster
   */
  rdsConnectPolicy: IManagedPolicy;
};

export class LambdaCaseUpdateEvent extends Construct {
  constructor(scope: Construct, id: string, props: LambdaProps) {
    super(scope, id);

    const orcabusEventBus = EventBus.fromEventBusName(this, 'EventBus', EVENT_BUS_NAME);

    const processEventLambda = new PythonFunction(this, 'ProcessEventLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/process_event_record.py',
      handler: 'handler',
      timeout: Duration.minutes(5),
    });
    processEventLambda.role?.addManagedPolicy(props.rdsConnectPolicy);

    orcabusEventBus.grantPutEventsTo(processEventLambda);
    processEventLambda.addEnvironment('EVENT_BUS_NAME', EVENT_BUS_NAME);

    new Rule(this, 'rule', {
      description: 'Triggers case update event processing lambda',
      eventBus: orcabusEventBus,
      eventPattern: {
        // @ts-expect-error - EventBridge pattern syntax allows this format
        source: [{ 'anything-but': 'orcabus.casemanager' }],
        detailType: ['CaseRelationshipUpdate'],
      },
      targets: [new LambdaFunction(processEventLambda)],
    });
  }
}
