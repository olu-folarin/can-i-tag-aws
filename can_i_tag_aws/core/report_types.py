"""TypedDict definitions for report structures and intermediate results.

These types document the shape of data flowing through the detection pipeline
and enable static type checking with mypy.
"""

from __future__ import annotations

from typing import TypedDict, Union

# ---------------------------------------------------------------------------
# Shared / Common
# ---------------------------------------------------------------------------


class ServiceEntry(TypedDict):
    """A service entry from the IAM Authorization Reference TOC."""

    name: str
    url: str


class UntaggableResource(TypedDict):
    """A single untaggable resource with reason."""

    resource: str
    service: str
    reason: str


class ConditionallyTaggableResource(TypedDict):
    """A resource type that supports tagging but has AWS-managed instances that cannot be tagged.

    The resource type passes standard taggability checks, but specific AWS-managed
    default instances (e.g., default.redis7, default.mysql8.0) are read-only to the
    account holder. SCP tag enforcement must exclude the given ARN pattern.

    ``source`` records how the entry was derived: "heuristic" (from naming
    conventions and scraped ARN templates, no credentials) or "live" (confirmed
    against an AWS account via boto3).
    """

    resource: str
    service: str
    arn_pattern: str
    description: str
    source: str


# ---------------------------------------------------------------------------
# detect_api_taggable.py
# ---------------------------------------------------------------------------


class ResourceTypeInfo(TypedDict):
    """Return type for extract_resource_types_with_tagging_info()."""

    all_resources: list[str]
    resources_with_tag_condition: list[str]
    arn_templates: dict[str, str]


class TaggingActionInfo(TypedDict):
    """Return type for extract_tagging_actions_and_resources()."""

    tagging_actions: list[str]
    taggable_resources: list[str]


class ServiceAnalysis(TypedDict):
    """Successful return from analyze_service()."""

    name: str
    url: str
    service_prefix: str
    has_tagging_api: bool
    all_resources: list[str]
    taggable_resources: list[str]
    untaggable_resources: list[str]
    tagging_actions: list[str]
    resources_with_tag_condition: list[str]
    arn_templates: dict[str, str]


class ServiceAnalysisError(TypedDict):
    """Error return from analyze_service()."""

    name: str
    url: str
    error: str


ServiceAnalysisResult = Union[ServiceAnalysis, ServiceAnalysisError]


class ApiReportSummary(TypedDict):
    """Summary section of the API-level detection report."""

    total_services: int
    services_without_tagging_api: int
    services_with_tagging_api: int
    mixed_services: int
    total_untaggable_resources: int
    conditionally_taggable_resource_types: int


class MixedServiceDetail(TypedDict):
    """Detail entry for a service with both taggable and untaggable resources."""

    name: str
    taggable: list[str]
    conditionally_taggable: list[str]
    untaggable: list[str]


class ApiReport(TypedDict):
    """Full report from detect_api_taggable.build_report()."""

    summary: ApiReportSummary
    untaggable_resources: list[UntaggableResource]
    conditionally_taggable_resources: list[ConditionallyTaggableResource]
    services_without_tagging_api: list[str]
    mixed_services_detail: list[MixedServiceDetail]


# ---------------------------------------------------------------------------
# detect_service_level.py
# ---------------------------------------------------------------------------


class TaggingSupportSuccess(TypedDict):
    """Successful return from check_tagging_support()."""

    has_tagging: bool
    can_tag_only: bool
    tagging_actions: list[str]


class TaggingSupportError(TypedDict):
    """Error return from check_tagging_support()."""

    has_tagging: None
    error: str
    tagging_actions: list[str]


TaggingSupportResult = Union[TaggingSupportSuccess, TaggingSupportError]


class SvcReportSummary(TypedDict):
    """Summary section of the service-level report."""

    total_services: int
    taggable_services: int
    untaggable_services: int
    errors: int


class SvcServiceDetail(TypedDict):
    """Detail entry for an untaggable service."""

    name: str
    url: str


class SvcTaggableDetail(TypedDict):
    """Detail entry for a taggable service."""

    name: str
    tagging_actions: list[str]


class SvcDetailedSection(TypedDict):
    """Detailed breakdown in the service-level report."""

    untaggable: list[SvcServiceDetail]
    taggable: list[SvcTaggableDetail]


class SvcReport(TypedDict):
    """Full report from detect_service_level.build_report()."""

    summary: SvcReportSummary
    untaggable_services: list[str]
    taggable_services: list[str]
    detailed: SvcDetailedSection


# ---------------------------------------------------------------------------
# cfn_to_iam_mapper.py
# ---------------------------------------------------------------------------


class ServiceLevelData(TypedDict):
    """Data loaded from service_level_untaggable.json."""

    untaggable_services: list[str]
    taggable_services: list[str]


class MatchedServiceData(TypedDict):
    """Classification entry for a service matched to IAM."""

    matched_service: str
    resources: list[str]


class UnknownServiceData(TypedDict):
    """Classification entry for a service with no IAM match."""

    resources: list[str]


class ClassificationResults(TypedDict):
    """Return type for identify_resource_level_untaggables()."""

    in_taggable_services: dict[str, MatchedServiceData]
    in_untaggable_services: dict[str, MatchedServiceData]
    unknown_services: dict[str, UnknownServiceData]


class CfnReportSummary(TypedDict):
    """Summary section of the CFN mapper report."""

    services_with_tagging_api: int
    resources_in_taggable_services: int
    services_without_tagging_api: int
    resources_in_untaggable_services: int
    unknown_services: int


class CfnReport(TypedDict):
    """Full report from cfn_to_iam_mapper.build_report()."""

    summary: CfnReportSummary
    untaggable_resources: list[str]
    resources_needing_verification: dict[str, list[str]]
    details: ClassificationResults


# ---------------------------------------------------------------------------
# diff_runs.py
# ---------------------------------------------------------------------------


class MetricChange(TypedDict):
    """Old vs new value for a single metric."""

    old: int
    new: int


class DiffReport(TypedDict):
    """Full report from diff_runs.compare_reports()."""

    added: list[tuple[str, str]]
    removed: list[tuple[str, str]]
    unchanged_count: int
    summary_changes: dict[str, MetricChange]
