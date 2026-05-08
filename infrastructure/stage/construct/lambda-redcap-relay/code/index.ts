import { timingSafeEqual } from 'crypto';
import { SecretsManagerClient, GetSecretValueCommand } from '@aws-sdk/client-secrets-manager';
import { SSMClient, GetParameterCommand } from '@aws-sdk/client-ssm';
import type { APIGatewayProxyEventV2, APIGatewayProxyResultV2 } from 'aws-lambda';

// --- Constants ---

const REDCAP_ENDPOINT = 'https://redcap.unimelb.edu.au/api/';
const REDCAP_REQUEST_TYPE_FIELD = 'rf_test_requested';

const CASE_MANAGER_DOMAIN = process.env.CASE_MANAGER_DOMAIN;
if (!CASE_MANAGER_DOMAIN) throw new Error('CASE_MANAGER_DOMAIN is not set');
const CASE_MANAGER_API_URL = `https://case.${CASE_MANAGER_DOMAIN}`;

// --- AWS clients ---

const ssmClient = new SSMClient({});
const ssmCache = new Map<string, string>();

const secretClient = new SecretsManagerClient({});
const secretCache = new Map<string, string>();

// --- AWS helpers ---

async function getSsmParameter(envVar: string): Promise<string> {
  const name = process.env[envVar];
  if (!name) throw new Error(`Environment variable ${envVar} is not set`);
  if (ssmCache.has(name)) return ssmCache.get(name)!;

  const response = await ssmClient.send(
    new GetParameterCommand({ Name: name, WithDecryption: true })
  );

  const value = response.Parameter?.Value;
  if (!value) throw new Error(`SSM parameter ${name} is empty`);

  ssmCache.set(name, value);
  return value;
}

async function getOrcabusServiceJwt(): Promise<string> {
  const secretName = process.env.ORCABUS_JWT_SECRET_NAME;
  if (!secretName) throw new Error('ORCABUS_JWT_SECRET_NAME is not set');

  const cacheKey = 'ORCABUS_JWT';
  if (secretCache.has(cacheKey)) return secretCache.get(cacheKey)!;

  const response = await secretClient.send(new GetSecretValueCommand({ SecretId: secretName }));
  if (!response.SecretString) throw new Error('Secret value is empty');

  const token = JSON.parse(response.SecretString)['id_token'] as string;
  secretCache.set(cacheKey, token);
  return token;
}

// --- REDCap helpers ---

async function fetchRequestType(recordId: string): Promise<string> {
  const apiToken = await getSsmParameter('REDCAP_TOKEN_SSM_PARAMETER_NAME');
  const body = new URLSearchParams({
    token: apiToken,
    content: 'record',
    format: 'json',
    records: recordId,
    fields: REDCAP_REQUEST_TYPE_FIELD,
  });

  const response = await fetch(REDCAP_ENDPOINT, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: body.toString(),
  });

  if (!response.ok) {
    throw new Error(`REDCap API error: ${response.status} ${response.statusText}`);
  }

  const records = (await response.json()) as Record<string, string>[];
  if (records.length !== 1) {
    throw new Error(`Expected 1 record but got ${records.length} for record: ${recordId}`);
  }

  const value = records[0][REDCAP_REQUEST_TYPE_FIELD];
  if (value === undefined) {
    throw new Error(`Field '${REDCAP_REQUEST_TYPE_FIELD}' not found in REDCap record: ${recordId}`);
  }

  return value;
}

// --- Case manager helpers ---

async function postToCaseManager(record: unknown): Promise<void> {
  const token = await getOrcabusServiceJwt();

  const response = await fetch(`${CASE_MANAGER_API_URL}/api/v1/case/`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify(record),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(`Case manager API error: ${response.status} - ${text}`);
  }

  console.log('Successfully posted record to case-manager');
}

// --- Request helpers ---

// Decode the request body, handling base64-encoded payloads from Lambda Function URLs.
function decodeRequestBody(event: APIGatewayProxyEventV2): URLSearchParams {
  const bodyStr = event.isBase64Encoded
    ? Buffer.from(event.body ?? '', 'base64').toString('utf-8')
    : (event.body ?? '');

  if (!bodyStr) throw new Error("Request doesn't contain body");
  return new URLSearchParams(bodyStr);
}

// Validate the shared-secret webhook token using a timing-safe comparison to prevent
// timing attacks. See https://developers.cloudflare.com/workers/examples/protect-against-timing-attacks/
async function validateWebhookToken(event: APIGatewayProxyEventV2): Promise<boolean> {
  const expected = Buffer.from(
    process.env.WEBHOOK_TOKEN ?? (await getSsmParameter('WEBHOOK_TOKEN_SSM_PARAMETER_NAME'))
  );
  const received = Buffer.from(event.queryStringParameters?.token ?? '');

  const lengthsMatch = expected.byteLength === received.byteLength;
  return lengthsMatch ? timingSafeEqual(received, expected) : !timingSafeEqual(received, received); // constant-time rejection when lengths differ
}

// --- Handler ---

export const handler = async (event: APIGatewayProxyEventV2): Promise<APIGatewayProxyResultV2> => {
  if (!(await validateWebhookToken(event))) {
    console.error('Rejected request: missing or invalid token');
    return { statusCode: 401 };
  }

  try {
    const body = decodeRequestBody(event);
    const recordId = body.get('record');

    if (!recordId) {
      console.error('Missing required fields in REDCap payload');
      return { statusCode: 400 };
    }

    const requestType = await fetchRequestType(recordId);
    await postToCaseManager({
      // TODO: Re-evaluate this to properly map the value
      requestFormId: recordId,
      type: requestType === '1' ? 'cttso' : 'wgts',
      studyType: 'clinical',
    });

    return { statusCode: 200 };
  } catch (error) {
    console.error(
      `Failed to process REDCap webhook: ${error instanceof Error ? error.message : 'Unknown error'}`
    );
    throw error;
  }
};
