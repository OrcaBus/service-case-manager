"""
HTTP client utilities for making authenticated requests to external OrcaBus services.

This module provides reusable functions for:
- Retrieving JWT tokens from AWS Secrets Manager
- Constructing authenticated HTTP headers
- Making authenticated HTTP GET requests with JSON response parsing
- Error handling for HTTP and authentication failures
"""

import logging
from typing import Dict, List, Optional, Union

import requests

from app.service.utils import get_service_jwt

logger = logging.getLogger(__name__)


def get_authenticated_headers() -> Dict[str, str]:
    """
    Get HTTP headers with JWT bearer token for authenticated requests to external services.

    Retrieves the service JWT token from AWS Secrets Manager and constructs
    the Authorization header for bearer token authentication.

    Returns:
        Dictionary with Authorization header containing Bearer token

    Raises:
        RuntimeError: JWT secret ARN not configured in ORCABUS_SERVICE_JWT_SECRET_ARN environment variable
        ValueError: JWT token (id_token) not found in secret

    Example:
        headers = get_authenticated_headers()
        # Returns: {"Authorization": "Bearer eyJhbGc..."}
    """
    jwt_token = get_service_jwt()
    return {"Authorization": f"Bearer {jwt_token}"}


def http_get_json(
    url: str, params: Optional[Dict[str, Union[str, List[str]]]] = None
) -> dict:
    """
    Perform authenticated HTTP GET request and return JSON response.

    Makes an authenticated HTTP GET request to the specified URL with optional
    query parameters. The request includes JWT bearer token authentication.

    Args:
        url: Full URL to query (e.g., "https://fastq.example.com/api/v1/readset/")
        params: Optional query parameters as key-value pairs. A list value is
            serialized by `requests` into repeated query keys, e.g.
            {"orcabusId": ["a", "b"]} -> ?orcabusId=a&orcabusId=b — useful for
            querying a service with multiple values for the same filter key.

    Returns:
        Parsed JSON response as dictionary

    Raises:
        RuntimeError: JWT secret ARN not configured (raised by get_authenticated_headers)
        ValueError: JWT token not found in secret (raised by get_authenticated_headers)
        requests.HTTPError: Non-200 status codes (4xx, 5xx)
        requests.RequestException: Network errors, timeout errors, or connection failures

    Example:
        # Simple GET request
        data = http_get_json("https://workflow.example.com/api/v1/workflow/")

        # GET request with query parameters
        data = http_get_json(
            "https://fastq.example.com/api/v1/readset/",
            params={"library_orcabus_id": "lib.xyz789"}
        )

        # GET request with a repeated query parameter (list value)
        data = http_get_json(
            "https://workflow.example.com/api/v1/workflowrun/",
            params={"orcabusId": ["wfr.a", "wfr.b"]}
        )
    """
    headers = get_authenticated_headers()

    try:
        logger.debug(f"Making authenticated GET request to: {url}")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        response.raise_for_status()  # Raises HTTPError for 4xx/5xx status codes
        return response.json()

    except requests.HTTPError as e:
        status_code = e.response.status_code if e.response else "unknown"
        logger.error(f"HTTP request failed with status {status_code} for URL {url}")
        raise

    except requests.RequestException as e:
        logger.error(f"HTTP request failed for URL {url}: {e}")
        raise
