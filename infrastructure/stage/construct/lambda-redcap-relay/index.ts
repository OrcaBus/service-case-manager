import path from 'path';
import { Construct } from 'constructs';
import { CfnOutput, Duration } from 'aws-cdk-lib';
import { Code, Function, FunctionUrlAuthType, Runtime } from 'aws-cdk-lib/aws-lambda';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { Alarm, ComparisonOperator, TreatMissingData } from 'aws-cdk-lib/aws-cloudwatch';

// This is SSM is manually created
const WEBHOOK_TOKEN_SSM_PARAMETER_NAME = '/orcabus/case-manager/redcap/webhook-token';
const REDCAP_TOKEN_SSM_PARAMETER_NAME = '/orcabus/case-manager/redcap/redcap-api-token';

// OrcaBus JWT
const ORCABUS_JWT_SECRET_NAME = 'orcabus/token-service-jwt'; // pragma: allowlist secret

export class LambdaRedCapRelayConstruct extends Construct {
  constructor(scope: Construct, id: string) {
    super(scope, id);
    const hostedZoneName = StringParameter.valueFromLookup(this, '/hosted_zone/umccr/name');

    const redCapRelayLambda = new Function(this, 'RedCapRelay', {
      runtime: Runtime.NODEJS_24_X,
      handler: 'index.handler',
      code: Code.fromDockerBuild(path.join(__dirname, 'code'), {
        file: 'lambda-build.Dockerfile',
        imagePath: 'usr/app/dist',
      }),
      reservedConcurrentExecutions: 5,
      timeout: Duration.seconds(5),
      environment: {
        WEBHOOK_TOKEN_SSM_PARAMETER_NAME: WEBHOOK_TOKEN_SSM_PARAMETER_NAME,
        REDCAP_TOKEN_SSM_PARAMETER_NAME: REDCAP_TOKEN_SSM_PARAMETER_NAME,
        ORCABUS_JWT_SECRET_NAME: ORCABUS_JWT_SECRET_NAME,
        CASE_MANAGER_DOMAIN: hostedZoneName,
      },
    });

    const webhookTokenSSM = StringParameter.fromSecureStringParameterAttributes(
      this,
      'WebhookTokenSSM',
      { parameterName: WEBHOOK_TOKEN_SSM_PARAMETER_NAME }
    );
    webhookTokenSSM.grantRead(redCapRelayLambda);

    const redcapTokenSSM = StringParameter.fromSecureStringParameterAttributes(
      this,
      'RedcapTokenSSM',
      { parameterName: REDCAP_TOKEN_SSM_PARAMETER_NAME }
    );
    redcapTokenSSM.grantRead(redCapRelayLambda);

    const orcabusJwt = Secret.fromSecretNameV2(this, 'OrcabusJwtSecret', ORCABUS_JWT_SECRET_NAME);
    orcabusJwt.grantRead(redCapRelayLambda);

    const fnUrl = redCapRelayLambda.addFunctionUrl({
      authType: FunctionUrlAuthType.NONE,
    });

    new CfnOutput(this, 'RedCapRelayFunctionUrl', {
      value: fnUrl.url,
      description: 'RedCap relay Lambda function URL — configure as: <url>?token=<secret>',
    });

    //  Alarm if > 50 invocations in 1 hour.
    new Alarm(this, 'HighInvocationsAlarm', {
      metric: redCapRelayLambda.metricInvocations({
        period: Duration.hours(1),
      }),
      threshold: 50,
      evaluationPeriods: 1,
      comparisonOperator: ComparisonOperator.GREATER_THAN_THRESHOLD,
      treatMissingData: TreatMissingData.NOT_BREACHING,
      alarmDescription: 'RedCap relay received >50 invocations in 1 hour — possible abuse',
    });

    // Throttles mean the reservedConcurrentExecutions=5 cap was hit — strong DoS signal.
    new Alarm(this, 'ThrottlesAlarm', {
      metric: redCapRelayLambda.metricThrottles({
        period: Duration.minutes(5),
      }),
      threshold: 3,
      evaluationPeriods: 3, // sustained throttling over 15 min
      comparisonOperator: ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
      treatMissingData: TreatMissingData.NOT_BREACHING,
      alarmDescription: 'RedCap relay is being throttled — possible flood or misconfigured caller',
    });
  }
}
