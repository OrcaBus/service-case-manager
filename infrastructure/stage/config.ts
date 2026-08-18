import { CaseManagerStackProps } from './stack';
import { getDefaultApiGatewayConfiguration } from '@orcabus/platform-cdk-constructs/api-gateway';
import { StageName } from '@orcabus/platform-cdk-constructs/shared-config/accounts';
import {
  SHARED_SECURITY_GROUP_NAME,
  VPC_LOOKUP_PROPS,
} from '@orcabus/platform-cdk-constructs/shared-config/networking';
import { WorkflowTypeOrcabusIdMap } from './construct/workflow-run-draft-publisher';

const getAppConfiguration = (stage: StageName): WorkflowTypeOrcabusIdMap => {
  const workflowOrcabusId: Record<StageName, WorkflowTypeOrcabusIdMap> = {
    BETA: { CTTSO_WORKFLOW_ORCABUS_ID: 'wfl.01KGNF62X5W5F9TV1EB4KSNX8E' },
    GAMMA: { CTTSO_WORKFLOW_ORCABUS_ID: '' },
    PROD: { CTTSO_WORKFLOW_ORCABUS_ID: 'wfl.01K50NMVB38JA6BT5DG6914K9Q' },
  };

  return workflowOrcabusId[stage];
};

export const getStackProps = (stage: StageName): CaseManagerStackProps => {
  return {
    vpcProps: VPC_LOOKUP_PROPS,
    lambdaSecurityGroupName: SHARED_SECURITY_GROUP_NAME,
    apiGatewayCognitoProps: {
      ...getDefaultApiGatewayConfiguration(stage),
      apiName: 'CaseManager',
      customDomainNamePrefix: 'case',
    },
    // Daily sync on every account stage
    isDailySyncRedCap: true,
    appConfiguration: getAppConfiguration(stage),
  };
};
