import { Construct } from 'constructs';
import { Duration } from 'aws-cdk-lib';
import {
  HttpMethod,
  HttpNoneAuthorizer,
  HttpRoute,
  HttpRouteKey,
} from 'aws-cdk-lib/aws-apigatewayv2';
import { PythonFunction, PythonFunctionProps } from '@aws-cdk/aws-lambda-python-alpha';
import { HttpLambdaIntegration } from 'aws-cdk-lib/aws-apigatewayv2-integrations';
import {
  OrcaBusApiGateway,
  OrcaBusApiGatewayProps,
} from '@orcabus/platform-cdk-constructs/api-gateway';
import {
  grantEventBusPublish,
  grantOrcabusServiceAccess,
  grantRdsConnect,
  grantRedcapToken,
} from '../utils';

type LambdaProps = {
  /**
   * The basic common lambda properties that it should inherit from
   */
  basicLambdaConfig: PythonFunctionProps;
  /**
   * The props for api-gateway
   */
  apiGatewayConstructProps: OrcaBusApiGatewayProps;
};

export class LambdaAPIConstruct extends Construct {
  private readonly lambda: PythonFunction;
  private readonly API_VERSION = 'v1';

  constructor(scope: Construct, id: string, lambdaProps: LambdaProps) {
    super(scope, id);

    const apiGW = new OrcaBusApiGateway(
      this,
      'OrcaBusAPI-CaseManager',
      lambdaProps.apiGatewayConstructProps
    );

    this.lambda = new PythonFunction(this, 'APILambda', {
      ...lambdaProps.basicLambdaConfig,
      index: 'handler/api.py',
      handler: 'handler',
      timeout: Duration.seconds(28),
      memorySize: 1024,
    });
    grantRdsConnect(this.lambda);
    grantRedcapToken(this.lambda);
    grantOrcabusServiceAccess(this.lambda);
    grantEventBusPublish(this.lambda);

    // add some integration to the http api gw
    const apiIntegration = new HttpLambdaIntegration('ApiLambdaIntegration', this.lambda);

    // Routes for API schemas
    new HttpRoute(this, 'GetSchemaHttpRoute', {
      httpApi: apiGW.httpApi,
      integration: apiIntegration,
      authorizer: new HttpNoneAuthorizer(), // No auth needed for schema
      routeKey: HttpRouteKey.with(`/schema/{PROXY+}`, HttpMethod.GET),
    });

    new HttpRoute(this, 'GetHttpRoute', {
      httpApi: apiGW.httpApi,
      integration: apiIntegration,
      routeKey: HttpRouteKey.with(`/api/${this.API_VERSION}/{PROXY+}`, HttpMethod.GET),
    });
    new HttpRoute(this, 'PostHttpRoute', {
      httpApi: apiGW.httpApi,
      integration: apiIntegration,
      routeKey: HttpRouteKey.with(`/api/${this.API_VERSION}/{PROXY+}`, HttpMethod.POST),
    });
    new HttpRoute(this, 'PatchHttpRoute', {
      httpApi: apiGW.httpApi,
      integration: apiIntegration,
      routeKey: HttpRouteKey.with(`/api/${this.API_VERSION}/{PROXY+}`, HttpMethod.PATCH),
    });
    new HttpRoute(this, 'DeleteHttpRoute', {
      httpApi: apiGW.httpApi,
      integration: apiIntegration,
      routeKey: HttpRouteKey.with(`/api/${this.API_VERSION}/{PROXY+}`, HttpMethod.DELETE),
    });

    // External-entity paths use Amazon Verified Permissions via the auth-stack Lambda authorizer.
    // More specific routes take precedence over the {PROXY+} wildcards above.
    new HttpRoute(this, 'PostExternalEntityCollectionHttpRoute', {
      httpApi: apiGW.httpApi,
      integration: apiIntegration,
      authorizer: apiGW.authStackHttpLambdaAuthorizer,
      routeKey: HttpRouteKey.with(
        `/api/${this.API_VERSION}/case/{orcabusId}/external-entity/{PROXY+}`,
        HttpMethod.POST
      ),
    });
    new HttpRoute(this, 'DeleteExternalEntityItemHttpRoute', {
      httpApi: apiGW.httpApi,
      integration: apiIntegration,
      authorizer: apiGW.authStackHttpLambdaAuthorizer,
      routeKey: HttpRouteKey.with(
        `/api/${this.API_VERSION}/case/{orcabusId}/external-entity/{externalEntityOrcabusId}/{PROXY+}`,
        HttpMethod.DELETE
      ),
    });
  }
}
