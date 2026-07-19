#!/usr/bin/env python3
"""
[SUPPLEMENTARY] Map CloudFormation resource types to tagging status.

This script maps CFN resource types to their tagging support status by
cross-referencing with IAM service data. Useful for IaC teams.

For authoritative resource-level detection, use detect_api_taggable.py instead.

Related scripts:
- detect_api_taggable.py [PRIMARY] - Authoritative resource-level detection
- detect_service_level.py [SECONDARY] - Quick service-level check
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from rich.table import Table

from can_i_tag_aws.core.cache_config import get_cached_session
from can_i_tag_aws.core.constants import CFN_SPEC_URL, DEFAULT_HTTP_TIMEOUT
from can_i_tag_aws.core.paths import OUTPUT_DIR
from can_i_tag_aws.core.report_types import CfnReport, ClassificationResults, ServiceLevelData
from can_i_tag_aws.core.service_mapping import CFN_TO_IAM_SERVICE, normalize_for_fuzzy_match

console = Console()
session = get_cached_session()


def load_service_level_data(output_dir: Path) -> ServiceLevelData:
    """Load the service-level untaggable data."""
    service_file = output_dir / "service_level_untaggable.json"
    if service_file.exists():
        with open(service_file) as f:
            return json.load(f)  # type: ignore[no-any-return]
    return {"untaggable_services": [], "taggable_services": []}


def get_cfn_resources() -> dict:
    """Get all CFN resource types grouped by service."""
    spec = session.get(CFN_SPEC_URL, timeout=DEFAULT_HTTP_TIMEOUT).json()
    resource_types = spec.get("ResourceTypes", {})

    by_service: dict[str, list[str]] = {}
    for resource_type in resource_types.keys():
        parts = resource_type.split("::")
        if len(parts) >= 3:
            service = parts[1].lower()
            if service not in by_service:
                by_service[service] = []
            by_service[service].append(resource_type)

    return by_service


def match_service(cfn_prefix: str, service_list: list[str]) -> str | None:
    """Match a CFN prefix to an IAM service name using verified mapping first, then exact fuzzy fallback."""
    cfn_lower = cfn_prefix.lower()

    iam_name = CFN_TO_IAM_SERVICE.get(cfn_lower)
    if iam_name and iam_name in service_list:
        return iam_name

    cfn_norm = normalize_for_fuzzy_match(cfn_lower)
    for svc in service_list:
        if normalize_for_fuzzy_match(svc) == cfn_norm:
            return svc

    return None


def identify_resource_level_untaggables(
    cfn_resources: dict[str, list[str]],
    service_data: ServiceLevelData,
) -> ClassificationResults:
    """Identify resources in untaggable vs taggable services using verified mapping."""
    taggable_services = service_data.get("taggable_services", [])
    untaggable_services = service_data.get("untaggable_services", [])

    results: ClassificationResults = {
        "in_taggable_services": {},
        "in_untaggable_services": {},
        "unknown_services": {},
    }

    for service, resources in cfn_resources.items():
        matched_taggable = match_service(service, taggable_services)
        matched_untaggable = match_service(service, untaggable_services)

        if matched_taggable and not matched_untaggable:
            results["in_taggable_services"][service] = {
                "matched_service": matched_taggable,
                "resources": resources,
            }
        elif matched_untaggable:
            results["in_untaggable_services"][service] = {
                "matched_service": matched_untaggable,
                "resources": resources,
            }
        else:
            results["unknown_services"][service] = {
                "resources": resources,
            }

    return results


def build_report(results: ClassificationResults) -> CfnReport:
    """Build the resource-level analysis report from classification results."""
    taggable_svc_resources = sum(len(v["resources"]) for v in results["in_taggable_services"].values())
    untaggable_svc_resources = sum(len(v["resources"]) for v in results["in_untaggable_services"].values())

    all_untaggable_resources = []
    for _service, data in sorted(results["in_untaggable_services"].items()):
        all_untaggable_resources.extend(data["resources"])

    return {
        "summary": {
            "services_with_tagging_api": len(results["in_taggable_services"]),
            "resources_in_taggable_services": taggable_svc_resources,
            "services_without_tagging_api": len(results["in_untaggable_services"]),
            "resources_in_untaggable_services": untaggable_svc_resources,
            "unknown_services": len(results["unknown_services"]),
        },
        "untaggable_resources": sorted(all_untaggable_resources),
        "resources_needing_verification": {
            service: data["resources"] for service, data in results["in_taggable_services"].items()
        },
        "details": results,
    }


def display_results(results: ClassificationResults, report: CfnReport) -> None:
    """Display the analysis results to the console."""
    console.print("\n[bold cyan]═══ RESOURCE-LEVEL ANALYSIS ═══[/bold cyan]\n")

    summary = report["summary"]

    table = Table(title="Resource Distribution")
    table.add_column("Category", style="cyan")
    table.add_column("Services", style="magenta")
    table.add_column("Resources", style="green")

    table.add_row(
        "In taggable services",
        str(summary["services_with_tagging_api"]),
        str(summary["resources_in_taggable_services"]),
    )
    table.add_row(
        "In untaggable services",
        str(summary["services_without_tagging_api"]),
        str(summary["resources_in_untaggable_services"]),
    )
    table.add_row(
        "Unknown services",
        str(summary["unknown_services"]),
        str(len(report.get("resources_needing_verification", {}))),
    )

    console.print(table)

    console.print("\n[bold red]RESOURCES IN UNTAGGABLE SERVICES[/bold red]")
    console.print("[dim]All resources in these services cannot be tagged[/dim]\n")

    for service, data in sorted(results["in_untaggable_services"].items()):
        console.print(f"[yellow]{service}[/yellow] ({data['matched_service']})")
        for r in data["resources"]:
            console.print(f"  - {r}")

    console.print(f"\n[bold]Total resources in untaggable services: {len(report['untaggable_resources'])}[/bold]")
    console.print("\n[yellow]Note: Resources in taggable services need manual verification[/yellow]")
    console.print("[yellow]to determine which specific resources don't support tagging.[/yellow]")


def main():
    console.print("[bold]Resource-Level Untaggable Detection[/bold]\n")

    output_dir = OUTPUT_DIR

    service_data = load_service_level_data(output_dir)

    if not service_data.get("untaggable_services"):
        console.print("[red]Run detect_service_level.py first to generate service data[/red]")
        return

    console.print(f"[green]Loaded {len(service_data['taggable_services'])} taggable services[/green]")
    console.print(f"[green]Loaded {len(service_data['untaggable_services'])} untaggable services[/green]")

    console.print("[blue]Fetching CloudFormation resource types...[/blue]")
    cfn_resources = get_cfn_resources()
    total_resources = sum(len(r) for r in cfn_resources.values())
    console.print(f"[green]Found {total_resources} resource types across {len(cfn_resources)} services[/green]")

    results = identify_resource_level_untaggables(cfn_resources, service_data)
    report = build_report(results)

    display_results(results, report)

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "resource_level_analysis.json"
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2)
    console.print(f"\n[green]Report saved to {output_file}[/green]")


if __name__ == "__main__":
    main()
