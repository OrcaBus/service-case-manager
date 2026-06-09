import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { formatRdsPolicyName } from '@orcabus/platform-cdk-constructs/shared-config/database';
import { SqsQueue } from 'aws-cdk-lib/aws-events-targets';
import { EventBus, Rule } from 'aws-cdk-lib/aws-events';
import { EVENT_BUS_NAME } from '@orcabus/platform-cdk-constructs/shared-config/event-bridge';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { JWT_SECRET_NAME } from '@orcabus/platform-cdk-constructs/shared-config/secrets';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { Queue, QueueEncryption } from 'aws-cdk-lib/aws-sqs';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';

type MetadataEntityLinkLambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
};

/**
 * Lambda triggered by EventBridge on MetadataStateChange events from orcabus.metadatamanager
 */
export class LambdaMetadataEntityLinkConstruct extends Construct {
  readonly lambda: PythonFunction;
  constructor(scope: Construct, id: string, props: MetadataEntityLinkLambdaProps) {
    super(scope, id);

    this.lambda = new PythonFunction(this, 'CaseMetadataLinkLambda', {
      ...props.basicLambdaConfig,
      index: 'handler/metadata_manager_linking.py',
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

    // pass the domain name for other services
    const hostedZoneName = StringParameter.valueFromLookup(this, '/hosted_zone/umccr/name');
    this.lambda.addEnvironment('HOSTED_ZONE_NAME', hostedZoneName);

    // allow lambda to retrieve the service user JWT
    const serviceUserJwtSecret = Secret.fromSecretNameV2(
      this,
      'serviceUserJwtSecret',
      JWT_SECRET_NAME
    );
    this.lambda.addEnvironment('ORCABUS_SERVICE_JWT_SECRET_ARN', serviceUserJwtSecret.secretArn);
    serviceUserJwtSecret.grantRead(this.lambda);

    const orcabusEventBus = EventBus.fromEventBusName(this, 'EventBus', EVENT_BUS_NAME);
    orcabusEventBus.grantPutEventsTo(this.lambda);
    this.lambda.addEnvironment('EVENT_BUS_NAME', EVENT_BUS_NAME);

    // Dead-letter queue: receives messages that fail after maxReceiveCount attempts
    const metadataLinkDlq = new Queue(this, 'MetadataEntityLinkDlq', {
      queueName: 'CaseManagerMetadataEntityLinkDlq',
      encryption: QueueEncryption.SQS_MANAGED,
      retentionPeriod: Duration.days(14),
    });

    // Main queue: EventBridge delivers events here; Lambda polls via event source mapping.
    // visibilityTimeout must be >= Lambda timeout (15 min) to prevent redelivery mid-execution.
    const metadataLinkQueue = new Queue(this, 'MetadataEntityLinkQueue', {
      queueName: 'CaseManagerMetadataEntityLinkQueue',
      encryption: QueueEncryption.SQS_MANAGED,
      visibilityTimeout: Duration.minutes(15),
      retentionPeriod: Duration.days(14),
      deadLetterQueue: {
        queue: metadataLinkDlq,
        // On ObjectDoesNotExist the Lambda extends visibility to ~11h 45min then raises,
        // so 3 attempts = at least 24 hour retries before giving up (daily REDCap should already sync at least once).
        maxReceiveCount: 3,
      },
    });

    // Grant Lambda permission to extend message visibility (used for 12h retry on case-not-found)
    metadataLinkQueue.grantConsumeMessages(this.lambda);
    this.lambda.addEnvironment('METADATA_MANAGER_LINKING_QUEUE_URL', metadataLinkQueue.queueUrl);

    // Event source mapping: SQS invokes Lambda per message (batchSize=1 for independent processing)
    this.lambda.addEventSource(
      new SqsEventSource(metadataLinkQueue, {
        batchSize: 1,
      })
    );

    // EventBridge rule: deliver MetadataStateChange events into SQS
    new Rule(this, 'MetadataEntityLinkEventRule', {
      eventBus: orcabusEventBus,
      description:
        'Deliver MetadataStateChange events from orcabus.metadatamanager into SQS for Lambda processing',
      eventPattern: {
        source: ['orcabus.metadatamanager'],
        detailType: ['MetadataStateChange'],
      },
      targets: [new SqsQueue(metadataLinkQueue)],
    });
  }
}
