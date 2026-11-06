import { Construct } from 'constructs';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { Duration } from 'aws-cdk-lib';
import { SqsQueue } from 'aws-cdk-lib/aws-events-targets';
import { Rule } from 'aws-cdk-lib/aws-events';
import { Queue, QueueEncryption } from 'aws-cdk-lib/aws-sqs';
import { SqsEventSource } from 'aws-cdk-lib/aws-lambda-event-sources';
import { grantEventBusPublish, grantOrcabusServiceAccess, grantRdsConnect } from '../utils';

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
    grantRdsConnect(this.lambda);
    grantOrcabusServiceAccess(this.lambda);
    const orcabusEventBus = grantEventBusPublish(this.lambda);

    // Dead-letter queue: receives messages that fail after maxReceiveCount attempts
    const metadataLinkDlq = new Queue(this, 'MetadataEntityLinkDlq', {
      queueName: 'CaseManagerMetadataEntityLinkDlq',
      encryption: QueueEncryption.SQS_MANAGED,
      enforceSSL: true,
      retentionPeriod: Duration.days(14),
    });

    // Main queue: EventBridge delivers events here; Lambda polls via event source mapping.
    // visibilityTimeout must be >= Lambda timeout (15 min) to prevent redelivery mid-execution.
    const metadataLinkQueue = new Queue(this, 'MetadataEntityLinkQueue', {
      queueName: 'CaseManagerMetadataEntityLinkQueue',
      encryption: QueueEncryption.SQS_MANAGED,
      enforceSSL: true,
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
