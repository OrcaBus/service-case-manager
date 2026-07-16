import { App, Validations } from 'aws-cdk-lib';
import { AwsSolutionsChecks } from 'cdk-nag';
import { StatelessStack } from '../infrastructure/toolchain/stateless-stack';

describe('cdk-nag-stateless-toolchain-stack', () => {
  const app = new App({});

  const statelessStack = new StatelessStack(app, 'StatelessStack', {
    env: {
      account: '123456789',
      region: 'ap-southeast-2',
    },
  });

  Validations.of(statelessStack).acknowledge({
    id: 'AwsSolutions-IAM4',
    reason: 'Allow CDK Pipeline',
  });
  Validations.of(statelessStack).acknowledge({
    id: 'AwsSolutions-IAM5',
    reason: 'Allow CDK Pipeline',
  });
  Validations.of(statelessStack).acknowledge({
    id: 'AwsSolutions-S1',
    reason: 'Allow CDK Pipeline',
  });
  Validations.of(statelessStack).acknowledge({
    id: 'AwsSolutions-KMS5',
    reason: 'Allow CDK Pipeline',
  });
  Validations.of(statelessStack).acknowledge({
    id: 'AwsSolutions-CB3',
    reason: 'Allow CDK Pipeline',
  });

  const report = new AwsSolutionsChecks(app).validateScope(statelessStack);

  test(`cdk-nag AwsSolutions Pack errors`, () => {
    const errors = report.violations.filter((v) => v.severity === 'error');
    expect(errors).toHaveLength(0);
  });

  test(`cdk-nag AwsSolutions Pack warnings`, () => {
    const warnings = report.violations.filter((v) => v.severity === 'warning');
    expect(warnings).toHaveLength(0);
  });
});
