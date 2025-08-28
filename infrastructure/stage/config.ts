import { CaseManagerStackProps } from './stack';
import { getDefaultApiGatewayConfiguration } from '@orcabus/platform-cdk-constructs/api-gateway';
import { StageName } from '@orcabus/platform-cdk-constructs/shared-config/accounts';
import {
  SHARED_SECURITY_GROUP_NAME,
  VPC_LOOKUP_PROPS,
} from '@orcabus/platform-cdk-constructs/shared-config/networking';

export const getStackProps = (stage: StageName): CaseManagerStackProps => {
  return {
    vpcProps: VPC_LOOKUP_PROPS,
    lambdaSecurityGroupName: SHARED_SECURITY_GROUP_NAME,
    apiGatewayCognitoProps: {
      ...getDefaultApiGatewayConfiguration(stage),
      apiName: 'CaseManager',
      customDomainNamePrefix: 'case',
    },
  };
};
