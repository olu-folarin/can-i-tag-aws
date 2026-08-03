"""
Integration tests that hit real AWS documentation.

These tests verify:
1. AWS doc URLs are accessible
2. Expected HTML structure hasn't changed
3. We can parse real service pages correctly

Run with: pytest tests/test_integration.py -v
"""

from functools import lru_cache

import pytest
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from can_i_tag_aws.core.constants import (
    CFN_SPEC_URL,
    DEFAULT_HTTP_TIMEOUT,
    SERVICE_AUTH_REF_BASE,
    SERVICE_AUTH_REF_TOC,
)

pytestmark = pytest.mark.integration

USER_AGENT = "can-i-tag-aws-tests (+https://github.com/olu-folarin/can-i-tag-aws)"


@lru_cache(maxsize=1)
def _session() -> requests.Session:
    """Session that retries the throttling responses AWS docs returns to CI runners.

    Requests from shared CI address ranges are occasionally answered with 403 or
    429 rather than the page, and the body then parses as a document with no
    services in it. Retrying with backoff keeps that from being reported as a
    change in the AWS documentation.
    """
    retry = Retry(
        total=4,
        backoff_factor=1,
        status_forcelist=(403, 429, 500, 502, 503, 504),
        allowed_methods=("GET",),
        respect_retry_after_header=True,
        raise_on_status=False,
    )
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT
    session.mount("https://", HTTPAdapter(max_retries=retry))
    return session


def fetch(url: str) -> requests.Response:
    """GET a documentation URL, failing loudly if it was not actually served."""
    response = _session().get(url, timeout=DEFAULT_HTTP_TIMEOUT)
    assert response.status_code == 200, f"{url} returned HTTP {response.status_code} after retries"
    return response


@lru_cache(maxsize=1)
def _toc_service_urls() -> dict[str, str]:
    """Map each service's IAM prefix to its list page URL, read live from the TOC.

    AWS periodically renames the ``list_*.html`` page slugs (e.g.
    ``list_amazonec2.html`` -> ``list_ec2.html``), but the IAM service prefix
    shown in parentheses in each TOC link (e.g. ``Amazon EC2 (ec2)``) is stable.
    Resolving URLs by that prefix keeps these tests self-healing across renames.
    """
    from bs4 import BeautifulSoup

    response = fetch(SERVICE_AUTH_REF_TOC)
    soup = BeautifulSoup(response.text, "lxml")

    urls: dict[str, str] = {}
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not isinstance(href, str):
            continue
        if "list_" not in href or not href.endswith(".html"):
            continue
        text = link.get_text(strip=True)
        if text.endswith(")") and "(" in text:
            prefix = text[text.rindex("(") + 1 : -1].strip()
            clean_href = href.lstrip("./")
            urls[prefix] = f"{SERVICE_AUTH_REF_BASE}/{clean_href}"
    return urls


def service_url(prefix: str) -> str:
    """Resolve a service's list page URL from the live TOC by IAM prefix."""
    urls = _toc_service_urls()
    assert prefix in urls, f"Service prefix '{prefix}' not found in TOC"
    return urls[prefix]


class TestAWSDocAccessibility:
    """Test that AWS documentation URLs are accessible."""

    def test_iam_service_auth_ref_toc_accessible(self):
        """Verify IAM Service Authorization Reference TOC is accessible."""
        response = fetch(SERVICE_AUTH_REF_TOC)
        assert "Actions, resources, and condition keys" in response.text

    def test_cfn_spec_accessible(self):
        """Verify CloudFormation spec is accessible."""
        data = fetch(CFN_SPEC_URL).json()
        assert "ResourceTypes" in data


class TestAWSDocStructure:
    """Test that AWS documentation structure matches expectations."""

    def test_service_list_contains_expected_count(self):
        """Verify we find a reasonable number of services."""
        from bs4 import BeautifulSoup

        response = fetch(SERVICE_AUTH_REF_TOC)
        soup = BeautifulSoup(response.text, "lxml")

        services = []
        for link in soup.find_all("a", href=True):
            href = link.get("href", "")
            if "list_" in href and href.endswith(".html"):
                services.append(link.get_text(strip=True))

        assert len(services) >= 400, f"Expected 400+ services, found {len(services)}"

    def test_sample_service_page_has_expected_structure(self):
        """Verify a sample service page has expected tables."""
        from bs4 import BeautifulSoup

        ec2_url = service_url("ec2")
        response = fetch(ec2_url)
        soup = BeautifulSoup(response.text, "lxml")

        tables = soup.find_all("table")
        assert len(tables) >= 2, "Expected at least 2 tables (actions, resources)"

        text = soup.get_text().lower()
        assert "actions defined by" in text
        assert "resource types defined by" in text

    def test_cfn_spec_has_expected_resource_count(self):
        """Verify CFN spec has a reasonable number of resource types."""
        data = fetch(CFN_SPEC_URL).json()

        resource_types = data.get("ResourceTypes", {})
        assert len(resource_types) >= 1000, f"Expected 1000+ resources, found {len(resource_types)}"


class TestSampleServiceParsing:
    """Test parsing of known service pages."""

    def test_ec2_has_tagging_actions(self):
        """Verify EC2 page shows tagging support."""
        from bs4 import BeautifulSoup

        ec2_url = service_url("ec2")
        response = fetch(ec2_url)
        soup = BeautifulSoup(response.text, "lxml")

        text = soup.get_text().lower()
        assert "createtags" in text or "tagresource" in text

    def test_health_has_no_tagging_actions(self):
        """Verify AWS Health (a known untaggable service) has no tagging actions."""
        from bs4 import BeautifulSoup

        health_url = service_url("health")
        response = fetch(health_url)
        soup = BeautifulSoup(response.text, "lxml")

        text = soup.get_text().lower()
        assert "tagresource" not in text
        assert "createtags" not in text
