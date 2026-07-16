import { App, Stack, Validations } from 'aws-cdk-lib';
import { AwsSolutionsChecks } from 'cdk-nag';
import { CaseManagerStack } from '../infrastructure/stage/stack';
import { getStackProps } from '../infrastructure/stage/config';

describe('cdk-nag-stateless-toolchain-stack', () => {
  const app = new App({});

  // You should configure all stack (sateless, stateful) to be tested
  const deployStack = new CaseManagerStack(app, 'DeployStack', {
    env: { account: '111111111111', region: 'ap-southeast-2' },
    ...getStackProps('PROD'),
  });

  applyNagSuppression(deployStack);

  const report = new AwsSolutionsChecks(app).validateScope(deployStack);

  test(`cdk-nag AwsSolutions Pack errors`, () => {
    const errors = report.violations.filter((v) => v.severity === 'error');
    expect(errors).toHaveLength(0);
  });

  test(`cdk-nag AwsSolutions Pack warnings`, () => {
    const warnings = report.violations.filter((v) => v.severity === 'warning');
    expect(warnings).toHaveLength(0);
  });
});

/**
 * apply nag suppression
 * @param stack
 */
function applyNagSuppression(stack: Stack) {
  Validations.of(stack).acknowledge({
    id: 'AwsSolutions-IAM4',
    reason: 'Allow the use of AWS managed policies.',
  });
  Validations.of(stack).acknowledge({
    id: 'AwsSolutions-IAM5',
    reason: 'Allow IAM entity contains wildcard permissions.',
  });
  Validations.of(stack).acknowledge({
    id: 'AwsSolutions-APIG4',
    reason: 'We have the default Cognito UserPool authorizer',
  });
  Validations.of(stack).acknowledge({
    id: 'AwsSolutions-L1',
    reason: 'Allow to use non latest version of runtime',
  });
}
