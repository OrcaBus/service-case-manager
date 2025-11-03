import os
import re
import boto3
import json

client = boto3.client('secretsmanager')


def get_service_jwt() -> str:
    """
    Get the service JWT from AWS Secrets Manager using the local endpoint provided by AWS Lambda.
    """
    secret_arn = os.environ.get('ORCABUS_SERVICE_JWT_SECRET_ARN')
    if not secret_arn:
        raise RuntimeError("SECRET_ARN environment variable is not set")

    response = client.get_secret_value(
        SecretId=secret_arn,
    )

    jwt = json.loads(response.get("SecretString", {})).get("id_token")
    if not jwt:
        raise ValueError("id_token not found in the secret")
    return jwt


def get_first_two_digits(s):
    """
    Extracts the first two consecutive digits from a string.

    Args:
        s (str): Input string.

    Returns:
        str or None: The first two digits found, or None if not found.
    """
    match = re.search(r'\d{2}', s)
    return match.group(0) if match else None
