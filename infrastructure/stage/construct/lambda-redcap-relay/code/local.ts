/**
 * Local dev runner — simulates a REDCap webhook invocation without deploying.
 *
 * Usage:
 *   npm run local
 */
import type { APIGatewayProxyEventV2 } from 'aws-lambda';
import { handler } from './index';

const MOCK_TOKEN = 'test-token';
process.env.WEBHOOK_TOKEN = MOCK_TOKEN;

const mockEvent: APIGatewayProxyEventV2 = {
  version: '2.0',
  routeKey: '$default',
  rawPath: '/',
  rawQueryString: `token=${MOCK_TOKEN}`,
  headers: {
    'content-type': 'application/x-www-form-urlencoded',
    host: 'localhost',
  },
  queryStringParameters: {
    token: MOCK_TOKEN,
  },
  requestContext: {
    accountId: 'local',
    apiId: 'local',
    domainName: 'localhost',
    domainPrefix: 'localhost',
    http: {
      method: 'POST',
      path: '/my/path',
      protocol: 'HTTP/1.1',
      sourceIp: '123.123.123.123',
      userAgent: 'agent',
    },
    requestId: 'local-request-id',
    routeKey: '$default',
    stage: '$default',
    time: new Date().toISOString(),
    timeEpoch: Date.now(),
  },
  body: 'cmVjb3JkPTEwMDAwMDg=',
  isBase64Encoded: true,
};

console.log('--- Running local REDCap webhook handler ---\n');

handler(mockEvent)
  .then((result) => {
    console.log('\n--- Result ---');
    console.log(JSON.stringify(result, null, 2));
  })
  .catch((err) => {
    console.error('\n--- Error ---');
    console.error(err);
    process.exit(1);
  });
