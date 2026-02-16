"""Shared AWS documentation fetching utilities.

Provides the canonical get_all_services() used by all detection scripts.
"""

from __future__ import annotations

from bs4 import BeautifulSoup
from rich.console import Console

from cache_config import get_cached_session
from constants import (
    DEFAULT_HTTP_TIMEOUT,
    MIN_EXPECTED_SERVICES,
    SERVICE_AUTH_REF_BASE,
    SERVICE_AUTH_REF_TOC,
)
from exceptions import AWSDocStructureError
from report_types import ServiceEntry

console = Console()
session = get_cached_session()


def get_all_services() -> list[ServiceEntry]:
    """Fetch all AWS services from IAM Authorization Reference.

    Returns a list of dicts with 'name' and 'url' keys.
    Raises AWSDocStructureError if the page yields fewer services than expected.
    """
    console.print("[blue]Fetching AWS services from IAM Authorization Reference...[/blue]")

    response = session.get(SERVICE_AUTH_REF_TOC, timeout=DEFAULT_HTTP_TIMEOUT)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")

    services: list[ServiceEntry] = []
    for link in soup.find_all("a", href=True):
        href = link.get("href", "")
        if not isinstance(href, str):
            continue
        if "list_" in href and href.endswith(".html"):
            service_name = link.get_text(strip=True)
            clean_href = href.lstrip("./")
            services.append(
                ServiceEntry(
                    name=service_name,
                    url=f"{SERVICE_AUTH_REF_BASE}/{clean_href}",
                )
            )

    if len(services) < MIN_EXPECTED_SERVICES:
        raise AWSDocStructureError(
            f"Expected at least {MIN_EXPECTED_SERVICES} services, found {len(services)}. "
            "AWS documentation structure may have changed."
        )

    return services
