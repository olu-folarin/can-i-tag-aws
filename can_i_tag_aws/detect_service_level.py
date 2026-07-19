#!/usr/bin/env python3
"""
[SECONDARY] Quick check for services without tagging API.

Use this for fast validation of service-level tagging support.
For authoritative resource-level detection, use detect_api_taggable.py instead.

Source: IAM Service Authorization Reference

Related scripts:
- detect_api_taggable.py [PRIMARY] - Authoritative resource-level detection
- cfn_to_iam_mapper.py [SUPPLEMENTARY] - CloudFormation resource mapping
"""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
from rich.console import Console
from rich.table import Table

from can_i_tag_aws.core.aws_docs import get_all_services
from can_i_tag_aws.core.cache_config import get_cached_session
from can_i_tag_aws.core.constants import DEFAULT_HTTP_TIMEOUT
from can_i_tag_aws.core.paths import OUTPUT_DIR
from can_i_tag_aws.core.report_types import SvcReport, TaggingSupportResult

console = Console()
session = get_cached_session()


def check_tagging_support(service_url: str) -> TaggingSupportResult:
    """Check if a service has tagging API actions."""
    try:
        response = session.get(service_url, timeout=DEFAULT_HTTP_TIMEOUT)
        page_text = response.text.lower()
        found_actions = []

        if "tagresource" in page_text:
            found_actions.append("TagResource")
        if "untagresource" in page_text:
            found_actions.append("UntagResource")
        if "createtags" in page_text:
            found_actions.append("CreateTags")
        if "deletetags" in page_text:
            found_actions.append("DeleteTags")
        if "addtags" in page_text:
            found_actions.append("AddTags*")
        if "removetags" in page_text:
            found_actions.append("RemoveTags*")

        can_tag = any(a in ["TagResource", "CreateTags", "AddTags*"] for a in found_actions)
        can_untag = any(a in ["UntagResource", "DeleteTags", "RemoveTags*"] for a in found_actions)

        return {
            "has_tagging": can_tag and can_untag,
            "can_tag_only": can_tag and not can_untag,
            "tagging_actions": found_actions,
        }
    except requests.RequestException as e:
        return {
            "has_tagging": None,
            "error": str(e),
            "tagging_actions": [],
        }


def classify_results(
    services: list[dict],
) -> tuple[list[dict], list[dict], list[dict]]:
    """Classify analyzed services into taggable, untaggable, and error buckets."""
    taggable = []
    untaggable = []
    errors = []

    for service in services:
        info = service.get("tagging_info", {})
        if info.get("error"):
            errors.append(service)
        elif info.get("has_tagging"):
            taggable.append(service)
        else:
            untaggable.append(service)

    return taggable, untaggable, errors


def build_report(
    services: list[dict],
    taggable: list[dict],
    untaggable: list[dict],
    errors: list[dict],
) -> SvcReport:
    """Build the service-level report from classified results."""
    return {
        "summary": {
            "total_services": len(services),
            "taggable_services": len(taggable),
            "untaggable_services": len(untaggable),
            "errors": len(errors),
        },
        "untaggable_services": [s["name"] for s in sorted(untaggable, key=lambda x: x["name"])],
        "taggable_services": [s["name"] for s in sorted(taggable, key=lambda x: x["name"])],
        "detailed": {
            "untaggable": [
                {
                    "name": s["name"],
                    "url": s["url"],
                }
                for s in untaggable
            ],
            "taggable": [
                {
                    "name": s["name"],
                    "tagging_actions": s["tagging_info"]["tagging_actions"],
                }
                for s in taggable
            ],
        },
    }


def display_results(
    taggable: list[dict],  # type: ignore[type-arg]
    untaggable: list[dict],  # type: ignore[type-arg]
    errors: list[dict],  # type: ignore[type-arg]
) -> None:
    """Display the analysis results to the console."""
    console.print("\n[bold cyan]═══ RESULTS ═══[/bold cyan]\n")

    table = Table(title="API-Level Tagging Support")
    table.add_column("Category", style="cyan")
    table.add_column("Count", style="magenta")

    table.add_row("Services WITH tagging API", str(len(taggable)))
    table.add_row("Services WITHOUT tagging API", str(len(untaggable)))
    table.add_row("Errors", str(len(errors)))

    console.print(table)

    console.print(f"\n[bold red]AWS SERVICES THAT DO NOT SUPPORT TAGGING ({len(untaggable)}):[/bold red]")
    console.print("[dim]These cannot be tagged via ANY method - CFN, Terraform, Console, or CLI[/dim]\n")

    for svc in sorted(untaggable, key=lambda x: x["name"]):
        console.print(f"  - {svc['name']}")

    console.print(
        f"\n[bold]BOTTOM LINE: {len(untaggable)} AWS services have no tagging support at the API level[/bold]"
    )


def main():
    console.print("[bold]AWS Services Without Tagging Support (API Level)[/bold]")
    console.print("[dim]Source of truth for SCP policies - applies to all creation methods[/dim]\n")

    services = get_all_services()
    console.print(f"[green]Found {len(services)} AWS services[/green]")

    console.print("[blue]Analyzing all services for tagging API support...[/blue]")

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(check_tagging_support, svc["url"]): svc for svc in services}

        completed = 0
        for future in as_completed(futures):
            completed += 1
            if completed % 50 == 0:
                console.print(f"  Progress: {completed}/{len(services)}")

            service = futures[future]
            result = future.result()
            service["tagging_info"] = result  # type: ignore[typeddict-unknown-key]

    taggable, untaggable, errors = classify_results(services)  # type: ignore[arg-type]
    report = build_report(services, taggable, untaggable, errors)  # type: ignore[arg-type]

    display_results(taggable, untaggable, errors)

    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "service_level_untaggable.json"
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2)
    console.print(f"\n[green]Report saved to {output_file}[/green]")


if __name__ == "__main__":
    main()
