import os
import re
import requests


def get_service_jwt() -> str:
    """
    Get the service JWT from AWS Secrets Manager using the local endpoint provided by AWS Lambda.
    """
    secret_arn = os.environ.get('ORCABUS_SERVICE_JWT_SECRET_ARN')
    if not secret_arn:
        raise RuntimeError("SECRET_ARN environment variable is not set")

    aws_session_token = os.environ.get("AWS_SESSION_TOKEN")
    if not aws_session_token:
        raise RuntimeError("AWS_SESSION_TOKEN environment variable is not set")

    url = f"http://localhost:2773/secretsmanager/get?secretId={secret_arn}"
    headers = {
        "X-Aws-Parameters-Secrets-Token": aws_session_token,
    }

    response = requests.get(url, headers=headers)
    response.raise_for_status()

    jwt = response.json().get("SecretString", {}).get("id_token")
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
