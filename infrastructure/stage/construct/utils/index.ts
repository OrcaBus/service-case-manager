import { PythonFunction } from '@aws-cdk/aws-lambda-python-alpha';
import { IEventBus, EventBus } from 'aws-cdk-lib/aws-events';
import { ManagedPolicy } from 'aws-cdk-lib/aws-iam';
import { Secret } from 'aws-cdk-lib/aws-secretsmanager';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { formatRdsPolicyName } from '@orcabus/platform-cdk-constructs/shared-config/database';
import { EVENT_BUS_NAME } from '@orcabus/platform-cdk-constructs/shared-config/event-bridge';
import { JWT_SECRET_NAME } from '@orcabus/platform-cdk-constructs/shared-config/secrets';

/**
 * Helpers that give a Lambda one capability: the environment variable(s) the Python code reads
 * together with the IAM permission needed to use it. Always call these on the Lambda after it is
 * created instead of calling `addEnvironment` / `grant*` by hand, so the two cannot drift apart.
 *
 * Keep `test/lambda-env.test.ts` in sync when a handler needs a new environment variable.
 */

export const CASE_MANAGER_DB_NAME = 'case_manager';
export const CASE_MANAGER_DB_USER = 'case_manager';

export const REDCAP_TOKEN_PARAMETER_NAME = '/orcabus/case-manager/redcap/redcap-api-token';

const HOSTED_ZONE_NAME_PARAMETER = '/hosted_zone/umccr/name';

/**
 * Allow the Lambda to connect to the case manager database with IAM authentication.
 * The DB connection settings (PG_*) come from `basicLambdaConfig` in the stack.
 */
export function grantRdsConnect(lambda: PythonFunction): void {
  lambda.role?.addManagedPolicy(
    ManagedPolicy.fromManagedPolicyName(
      lambda,
      'OrcabusRdsConnectPolicy',
      formatRdsPolicyName(CASE_MANAGER_DB_USER)
    )
  );
}

/**
 * Needed to call other OrcaBus services (sequence, workflow, metadata) over their API.
 * Sets HOSTED_ZONE_NAME (to build the service URLs) and ORCABUS_SERVICE_JWT_SECRET_ARN (the token).
 */
export function grantOrcabusServiceAccess(lambda: PythonFunction): void {
  const hostedZoneName = StringParameter.valueFromLookup(lambda, HOSTED_ZONE_NAME_PARAMETER);
  lambda.addEnvironment('HOSTED_ZONE_NAME', hostedZoneName);

  const serviceUserJwtSecret = Secret.fromSecretNameV2(
    lambda,
    'serviceUserJwtSecret',
    JWT_SECRET_NAME
  );
  lambda.addEnvironment('ORCABUS_SERVICE_JWT_SECRET_ARN', serviceUserJwtSecret.secretArn);
  serviceUserJwtSecret.grantRead(lambda);
}

/**
 * Needed to emit events to the OrcaBus event bus. Sets EVENT_BUS_NAME.
 * Returns the event bus so the caller can attach its trigger rule to it.
 */
export function grantEventBusPublish(lambda: PythonFunction): IEventBus {
  const orcabusEventBus = EventBus.fromEventBusName(lambda, 'EventBus', EVENT_BUS_NAME);
  orcabusEventBus.grantPutEventsTo(lambda);
  lambda.addEnvironment('EVENT_BUS_NAME', EVENT_BUS_NAME);
  return orcabusEventBus;
}

/**
 * Needed to call the REDCap API. Sets REDCAP_TOKEN_PARAMETER_NAME and allows reading the token.
 */
export function grantRedcapToken(lambda: PythonFunction): void {
  lambda.addEnvironment('REDCAP_TOKEN_PARAMETER_NAME', REDCAP_TOKEN_PARAMETER_NAME);
  StringParameter.fromSecureStringParameterAttributes(lambda, 'RedcapTokenSSM', {
    parameterName: REDCAP_TOKEN_PARAMETER_NAME,
  }).grantRead(lambda);
}
