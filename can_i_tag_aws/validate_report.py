#!/usr/bin/env python3
"""Validate a freshly generated detection report before it is published.

The scheduled workflow runs this after scraping and before opening the update
PR. Its job is to turn *silent data degradation* into a loud failure. The HTML
scrape can break in ways that still produce a plausibly shaped but wrong report
(for example an AWS column rename that quietly empties tag-condition detection).
The integration tests catch gross structural breaks; this catches the subtler
ones by asserting invariants on the output and guarding against an implausible
delta versus the previous run.

Two distinct outcomes, deliberately kept separate:

- **Broken** (a hard invariant fails): the report is almost certainly the
  product of a broken scrape rather than a real AWS change. Exit non-zero so the
  workflow refuses to publish it and alerts instead.
- **Large but plausible** (churn versus the previous run exceeds a threshold):
  the numbers are sane but the change is big enough to deserve a human. Exit 0
  and set ``needs_review=true`` so the workflow opens the PR without
  auto-merging.

Exit codes:
  0  passed the hard invariants (see ``needs_review`` for the merge decision)
  1  a hard invariant failed; do not publish
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

from can_i_tag_aws.core.constants import MIN_EXPECTED_SERVICES
from can_i_tag_aws.core.paths import OUTPUT_DIR
from can_i_tag_aws.diff_runs import (
    extract_untaggable_set,
    get_latest_history_files,
    load_report,
)

# Hard invariants. Violating any of these means the report looks broken, not
# merely changed. The bands are wide on purpose: they exist to catch collapse or
# total misclassification, not to second-guess normal week-to-week drift.
MIN_SERVICES = MIN_EXPECTED_SERVICES  # 400
MIN_SERVICES_WITH_TAGGING = 250
MIN_TOTAL_UNTAGGABLE = 200
MAX_TOTAL_UNTAGGABLE = 1500
MIN_CONDITIONALLY_TAGGABLE = 4

# Fraction of the untaggable set that may change (in either direction) between
# runs before the report is held back for human review rather than auto-merged.
DELTA_REVIEW_THRESHOLD = 0.25

# Removals are the dangerous direction: an untaggable resource dropping off the
# list means SCP/IAM tag enforcement would start applying to something that
# cannot be tagged, which is exactly the deployment breakage this tool exists to
# prevent. So removals get a much tighter, absolute trigger than overall churn:
# a small silent drop (well under the 25% band) still gets a human.
REMOVAL_REVIEW_ABS = 10
REMOVAL_REVIEW_RATIO = 0.05


def _all_service_names(report: dict) -> set[str]:
    """Every service string referenced anywhere in the report."""
    names: set[str] = set(report.get("services_without_tagging_api", []))
    for entry in report.get("mixed_services_detail", []):
        names.add(entry["name"])
    for entry in report.get("untaggable_resources", []):
        names.add(entry["service"])
    for entry in report.get("conditionally_taggable_resources", []):
        names.add(entry["service"])
    return names


def _has_service(report: dict, prefix_suffix: str) -> bool:
    """True if any service name carries the given IAM prefix, e.g. '(ec2)'.

    Matching on the prefix rather than the display name keeps the canaries stable
    across AWS renaming the human-readable service name.
    """
    return any(prefix_suffix in name for name in _all_service_names(report))


def check_invariants(report: dict) -> list[str]:
    """Return a list of invariant violations; empty means the report looks sane."""
    violations: list[str] = []
    summary = report.get("summary", {})

    total_services = summary.get("total_services", 0)
    if total_services < MIN_SERVICES:
        violations.append(f"total_services {total_services} < {MIN_SERVICES}")

    with_tagging = summary.get("services_with_tagging_api", 0)
    if with_tagging < MIN_SERVICES_WITH_TAGGING:
        violations.append(f"services_with_tagging_api {with_tagging} < {MIN_SERVICES_WITH_TAGGING}")

    total_untaggable = summary.get("total_untaggable_resources", 0)
    if not (MIN_TOTAL_UNTAGGABLE <= total_untaggable <= MAX_TOTAL_UNTAGGABLE):
        violations.append(
            f"total_untaggable_resources {total_untaggable} outside [{MIN_TOTAL_UNTAGGABLE}, {MAX_TOTAL_UNTAGGABLE}]"
        )

    cond = summary.get("conditionally_taggable_resource_types", 0)
    if cond < MIN_CONDITIONALLY_TAGGABLE:
        violations.append(f"conditionally_taggable_resource_types {cond} < {MIN_CONDITIONALLY_TAGGABLE}")

    # Anchor canaries: stable facts that only flip if the parser, not AWS, broke.
    if not _has_service(report, "(ec2)"):
        violations.append("anchor: no Amazon EC2 service found")
    if not _has_service(report, "(s3)"):
        violations.append("anchor: no Amazon S3 service found")

    ec2_instance_untaggable = any(
        "(ec2)" in entry["service"] and entry["resource"] == "instance"
        for entry in report.get("untaggable_resources", [])
    )
    if ec2_instance_untaggable:
        violations.append("anchor: EC2 'instance' classified untaggable (expected taggable)")

    elasticache_pg_conditional = any(
        "(elasticache)" in entry["service"] and entry["resource"] == "parametergroup"
        for entry in report.get("conditionally_taggable_resources", [])
    )
    if not elasticache_pg_conditional:
        violations.append("anchor: ElastiCache 'parametergroup' missing from conditionally_taggable")

    return violations


@dataclass
class DeltaAssessment:
    """Outcome of comparing the untaggable sets of two runs."""

    churn: float
    removed: int
    added: int
    needs_review: bool
    reason: str


def assess_delta(previous: dict | None, current: dict) -> DeltaAssessment:
    """Compare the untaggable sets of two runs and decide whether a human is needed.

    Review is triggered by any of: overall churn above the band, an absolute
    number of removals, or a removal ratio. The removal triggers are deliberately
    tighter than churn so a plausible-but-quietly-wrong run that silently drops a
    handful of untaggable resources does not auto-merge unreviewed. With no
    previous run there is no baseline, so nothing is flagged.
    """
    if previous is None:
        return DeltaAssessment(0.0, 0, 0, False, "")

    old_set = extract_untaggable_set(previous)
    new_set = extract_untaggable_set(current)
    if not old_set:
        return DeltaAssessment(0.0, 0, len(new_set), False, "")

    removed = old_set - new_set
    added = new_set - old_set
    churn = len(removed | added) / len(old_set)
    removed_ratio = len(removed) / len(old_set)

    reasons: list[str] = []
    if churn > DELTA_REVIEW_THRESHOLD:
        reasons.append(f"churn {churn:.0%} exceeds {DELTA_REVIEW_THRESHOLD:.0%}")
    if len(removed) >= REMOVAL_REVIEW_ABS:
        reasons.append(f"{len(removed)} untaggable resources removed (>= {REMOVAL_REVIEW_ABS})")
    if removed_ratio > REMOVAL_REVIEW_RATIO:
        reasons.append(f"removals {removed_ratio:.0%} exceed {REMOVAL_REVIEW_RATIO:.0%}")

    return DeltaAssessment(churn, len(removed), len(added), bool(reasons), "; ".join(reasons))


def _emit_output(assessment: DeltaAssessment) -> None:
    """Expose the merge decision to the workflow via GITHUB_OUTPUT."""
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a") as fh:
            fh.write(f"needs_review={'true' if assessment.needs_review else 'false'}\n")
            fh.write(f"review_reason={assessment.reason}\n")


def main() -> int:
    report_path = OUTPUT_DIR / "api_taggable_resources.json"
    if not report_path.exists():
        print(f"FAIL: report not found at {report_path}", file=sys.stderr)
        return 1

    current = load_report(report_path)

    violations = check_invariants(current)
    if violations:
        print("FAIL: report failed hard invariants (looks like a broken scrape):", file=sys.stderr)
        for v in violations:
            print(f"  - {v}", file=sys.stderr)
        return 1

    previous_file, _ = get_latest_history_files()
    previous = load_report(previous_file) if previous_file else None
    delta = assess_delta(previous, current)

    summary = current.get("summary", {})
    print("Report validation passed hard invariants.")
    print(f"  total_untaggable_resources: {summary.get('total_untaggable_resources')}")
    print(f"  conditionally_taggable_resource_types: {summary.get('conditionally_taggable_resource_types')}")
    print(f"  vs previous run: churn {delta.churn:.1%}, +{delta.added} / -{delta.removed}")
    if delta.needs_review:
        print(f"  holding for human review (no auto-merge): {delta.reason}")
    else:
        print("  change within thresholds: safe to auto-merge.")

    _emit_output(delta)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
