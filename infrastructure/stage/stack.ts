import path from 'path';
import { Construct } from 'constructs';
import { Stack, StackProps } from 'aws-cdk-lib';
import { Vpc, VpcLookupOptions, SecurityGroup } from 'aws-cdk-lib/aws-ec2';
import { Code, Runtime, Architecture, LayerVersion } from 'aws-cdk-lib/aws-lambda';
import { OrcaBusApiGatewayProps } from '@orcabus/platform-cdk-constructs/api-gateway';
import { LambdaMigrationConstruct } from './construct/lambda-migration';
import { LambdaAPIConstruct } from './construct/lambda-api';
import { StringParameter } from 'aws-cdk-lib/aws-ssm';
import { DB_CLUSTER_ENDPOINT_HOST_PARAMETER_NAME } from '@orcabus/platform-cdk-constructs/shared-config/database';
import { EventSchemaConstruct } from './construct/event-schema';
import { LambdaRedCapImportConstruct } from './construct/lambda-redcap-import';

export type CaseManagerStackProps = {
  /**
   * VPC (lookup props) that will be used by resources
   */
  vpcProps: VpcLookupOptions;
  /**
   * Existing security group name to be attached on lambdas
   */
  lambdaSecurityGroupName: string;
  /**
   * API Gateway props
   */
  apiGatewayCognitoProps: OrcaBusApiGatewayProps;
};

export class CaseManagerStack extends Stack {
  private readonly CASE_MANAGER_DB_NAME = 'case_manager';
  private readonly CASE_MANAGER_DB_USER = 'case_manager';

  constructor(scope: Construct, id: string, props: StackProps & CaseManagerStackProps) {
    super(scope, id, props);

    const vpc = Vpc.fromLookup(this, 'MainVpc', props.vpcProps);
    const lambdaSG = SecurityGroup.fromLookupByName(
      this,
      'LambdaSecurityGroup',
      props.lambdaSecurityGroupName,
      vpc
    );

    // despite of multiple lambda all of them will share the same dependencies
    const dependencyLayer = new LayerVersion(this, 'DependenciesLayer', {
      code: Code.fromDockerBuild(__dirname + '/../../', {
        file: 'case-manager/deps/Dockerfile.lambda_layer',
        imagePath: 'home/output',
      }),
      compatibleArchitectures: [Architecture.ARM_64],
      compatibleRuntimes: [Runtime.PYTHON_3_13],
    });

    // Grab the database cluster
    const clusterHostEndpoint = StringParameter.valueForStringParameter(
      this,
      DB_CLUSTER_ENDPOINT_HOST_PARAMETER_NAME
    );

    const basicLambdaConfig = {
      entry: path.join(__dirname, '../../case-manager'),
      runtime: Runtime.PYTHON_3_13,
      layers: [dependencyLayer],
      bundling: {
        assetExcludes: ['*__pycache__*', '*.DS_Store*', '*.idea*', '*.venv*'],
      },
      environment: {
        DJANGO_SETTINGS_MODULE: 'app.settings.aws',
        PG_HOST: clusterHostEndpoint,
        PG_USER: this.CASE_MANAGER_DB_USER,
        PG_DB_NAME: this.CASE_MANAGER_DB_NAME,
      },
      securityGroups: [lambdaSG],
      vpc: vpc,
      vpcSubnets: { subnets: vpc.privateSubnets },
      architecture: Architecture.ARM_64,
      memorySize: 1024,
    };

    new LambdaMigrationConstruct(this, 'MigrationLambda', {
      basicLambdaConfig: basicLambdaConfig,
    });

    const caseFinder = new LambdaRedCapImportConstruct(this, 'RedCapImportLambda', {
      basicLambdaConfig: basicLambdaConfig,
    });

    new LambdaAPIConstruct(this, 'APILambda', {
      basicLambdaConfig: basicLambdaConfig,
      apiGatewayConstructProps: props.apiGatewayCognitoProps,
      caseAutoInferLambda: caseFinder.lambda,
    });

    new EventSchemaConstruct(this, 'EventSchema');
  }
}
