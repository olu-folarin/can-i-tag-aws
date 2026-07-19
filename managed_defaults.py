"""Dynamic detection of AWS-managed default instances that cannot be tagged.

Some resource *types* support tagging, yet specific AWS-managed default
instances within them (for example ``default.redis7`` or the default RDS
parameter group) are owned by AWS rather than the account and reject
account-defined tags. SCP tag-enforcement policies must exclude those instances
or they block legitimate deployments that merely reference them.

AWS does not publish a machine-readable registry of these managed defaults, so
this module derives them without maintaining a per-service hardcoded list:

1. Heuristic (no credentials required). Resource types are matched against
   stable AWS naming conventions (parameter groups, option groups, AWS-managed
   IAM policies), and the exclusion ARN pattern is built from the resource
   type's own ARN template as scraped from the IAM Service Authorization
   Reference. Any newly added service that follows the same convention is
   therefore covered automatically, with no code change.

2. Live confirmation (optional, requires credentials). When boto3 and AWS
   credentials are available, managed defaults are enumerated directly from the
   account and merged in, upgrading the ``source`` of matching entries to
   ``"live"``.

The heuristic deliberately errs toward inclusion: adding a ``default.*``
exclusion for a service that turns out not to need one is harmless for SCP
enforcement, whereas missing one blocks real deployments.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from report_types import ConditionallyTaggableResource

# ---------------------------------------------------------------------------
# Heuristic rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ManagedDefaultRule:
    """A convention-based rule that flags a taggable resource type as having
    AWS-managed default instances that reject tags.

    ``matches`` receives the (normalized) resource type and the service prefix
    and returns whether the rule applies. ``instance_glob`` replaces the
    resource-id segment of the ARN template to describe the managed instances,
    and ``account`` optionally overrides the account segment (AWS-managed IAM
    policies live under the literal account ``aws``).
    """

    name: str
    description: str
    instance_glob: str
    matches: Callable[[str, str], bool]
    account: str | None = None


def _is_parameter_group(resource_type: str, service_prefix: str) -> bool:
    rt = resource_type.lower()
    return rt in {"pg", "cluster-pg"} or rt.endswith("parametergroup")


def _is_option_group(resource_type: str, service_prefix: str) -> bool:
    rt = resource_type.lower()
    return rt == "og" or rt.endswith("optiongroup")


def _is_aws_managed_iam_policy(resource_type: str, service_prefix: str) -> bool:
    return service_prefix.lower() == "iam" and resource_type.lower() == "policy"


RULES: list[ManagedDefaultRule] = [
    ManagedDefaultRule(
        name="parameter_group_default",
        description=(
            "AWS-managed default parameter groups (e.g., default.redis7, default.mysql8.0) "
            "are owned by AWS and reject account-defined tags"
        ),
        instance_glob="default.*",
        matches=_is_parameter_group,
    ),
    ManagedDefaultRule(
        name="option_group_default",
        description=(
            "AWS-managed default option groups (e.g., default:mysql-8-0) "
            "are owned by AWS and reject account-defined tags"
        ),
        instance_glob="default:*",
        matches=_is_option_group,
    ),
    ManagedDefaultRule(
        name="aws_managed_iam_policy",
        description=(
            "AWS-managed IAM policies (e.g., arn:aws:iam::aws:policy/ReadOnlyAccess) "
            "are owned by AWS and cannot be tagged by the account"
        ),
        instance_glob="*",
        matches=_is_aws_managed_iam_policy,
        account="aws",
    ),
]

# ---------------------------------------------------------------------------
# ARN pattern construction
# ---------------------------------------------------------------------------

_PLACEHOLDER = re.compile(r"\$\{[^}]*\}")


def build_arn_pattern(arn_template: str, rule: ManagedDefaultRule) -> str:
    """Turn a resource-type ARN template into an SCP exclusion pattern.

    The ARN template comes straight from the IAM Service Authorization Reference
    (for example
    ``arn:${Partition}:elasticache:${Region}:${Account}:parametergroup:${CacheParameterGroupName}``),
    so the service-specific delimiters are preserved. Well-known leading
    placeholders are normalized to wildcards, the trailing resource-id
    placeholder is replaced with the rule's instance glob, and any remaining
    placeholders collapse to ``*``.
    """
    arn = arn_template.strip()
    arn = arn.replace("${Partition}", "aws")
    arn = re.sub(r"\$\{Region\}", "*", arn)
    account_val = rule.account if rule.account is not None else "*"
    arn = re.sub(r"\$\{Account(Id)?\}", account_val, arn)

    placeholders = list(_PLACEHOLDER.finditer(arn))
    if placeholders:
        last = placeholders[-1]
        arn = arn[: last.start()] + rule.instance_glob + arn[last.end() :]

    return _PLACEHOLDER.sub("*", arn)


def _fallback_arn_pattern(service_prefix: str, resource_type: str, rule: ManagedDefaultRule) -> str:
    """Build a best-effort ARN pattern when the docs did not yield a template.

    IAM managed policies have a fixed, well-known shape. For everything else the
    common ``arn:aws:<service>:*:*:<type>:<instance>`` colon form is used.
    """
    if rule.account == "aws" and service_prefix.lower() == "iam":
        return "arn:aws:iam::aws:policy/*"
    account = rule.account if rule.account is not None else "*"
    return f"arn:aws:{service_prefix}:*:{account}:{resource_type}:{rule.instance_glob}"


# ---------------------------------------------------------------------------
# Heuristic detection
# ---------------------------------------------------------------------------


def detect_conditionally_taggable(
    service_name: str,
    service_prefix: str,
    taggable_resources: Iterable[str],
    arn_templates: dict[str, str],
) -> list[ConditionallyTaggableResource]:
    """Flag taggable resource types that carry AWS-managed default instances.

    Uses only data scraped from the IAM Service Authorization Reference, so it
    needs no AWS credentials.
    """
    results: list[ConditionallyTaggableResource] = []
    for resource_type in sorted(set(taggable_resources)):
        for rule in RULES:
            if not rule.matches(resource_type, service_prefix):
                continue
            template = arn_templates.get(resource_type, "")
            arn_pattern = (
                build_arn_pattern(template, rule)
                if template
                else _fallback_arn_pattern(service_prefix, resource_type, rule)
            )
            results.append(
                ConditionallyTaggableResource(
                    resource=resource_type,
                    service=service_name,
                    arn_pattern=arn_pattern,
                    description=rule.description,
                    source="heuristic",
                )
            )
            break
    return results


def build_conditionally_taggable(has_tagging_api: list[dict]) -> list[ConditionallyTaggableResource]:
    """Run the heuristic across every service that supports tagging."""
    results: list[ConditionallyTaggableResource] = []
    for svc in has_tagging_api:
        results.extend(
            detect_conditionally_taggable(
                svc["name"],
                svc.get("service_prefix", ""),
                svc.get("taggable_resources", []),
                svc.get("arn_templates", {}),
            )
        )
    return results


# ---------------------------------------------------------------------------
# Optional live enumeration (requires boto3 + AWS credentials)
# ---------------------------------------------------------------------------


def _dedupe_key(entry: ConditionallyTaggableResource) -> tuple[str, str, str]:
    return (entry["service"], entry["resource"], entry["arn_pattern"])


def merge_conditionally_taggable(
    heuristic: list[ConditionallyTaggableResource],
    live: list[ConditionallyTaggableResource],
) -> list[ConditionallyTaggableResource]:
    """Combine heuristic and live results, letting live confirmation win on overlap."""
    merged: dict[tuple[str, str, str], ConditionallyTaggableResource] = {}
    for entry in heuristic:
        merged[_dedupe_key(entry)] = entry
    for entry in live:
        merged[_dedupe_key(entry)] = entry
    return sorted(merged.values(), key=lambda e: (e["service"], e["resource"]))


def enumerate_live_managed_defaults(region: str = "us-east-1") -> list[ConditionallyTaggableResource]:
    """Enumerate AWS-managed defaults from a live account.

    Returns an empty list when boto3 or credentials are unavailable, so callers
    can invoke it unconditionally. Each backing service call is isolated: a
    permission error for one service does not abort the others.
    """
    try:
        import boto3
        from botocore.exceptions import BotoCoreError, ClientError, NoCredentialsError
    except ImportError:
        return []

    aws_errors = (BotoCoreError, ClientError, NoCredentialsError)
    found: list[ConditionallyTaggableResource] = []

    def _add(service: str, resource: str, arn_pattern: str, description: str) -> None:
        found.append(
            ConditionallyTaggableResource(
                resource=resource,
                service=service,
                arn_pattern=arn_pattern,
                description=description,
                source="live",
            )
        )

    # AWS-managed IAM policies are global and confirmable via a single call.
    try:
        iam = boto3.client("iam", region_name=region)
        paginator = iam.get_paginator("list_policies")
        for page in paginator.paginate(Scope="AWS", MaxItems=1):
            if page.get("Policies"):
                _add(
                    "AWS Identity and Access Management (IAM)",
                    "policy",
                    "arn:aws:iam::aws:policy/*",
                    "AWS-managed IAM policies confirmed present in account (cannot be tagged)",
                )
            break
    except aws_errors:
        pass

    # Default parameter/option groups follow the default.* / default:* convention.
    describe_calls = [
        ("Amazon RDS", "rds", "describe_db_parameter_groups", "DBParameterGroups", "DBParameterGroupName", "pg"),
        (
            "Amazon RDS",
            "rds",
            "describe_db_cluster_parameter_groups",
            "DBClusterParameterGroups",
            "DBClusterParameterGroupName",
            "cluster-pg",
        ),
        ("Amazon RDS", "rds", "describe_option_groups", "OptionGroupsList", "OptionGroupName", "og"),
        (
            "Amazon ElastiCache",
            "elasticache",
            "describe_cache_parameter_groups",
            "CacheParameterGroups",
            "CacheParameterGroupName",
            "parametergroup",
        ),
        (
            "Amazon Redshift",
            "redshift",
            "describe_cluster_parameter_groups",
            "ParameterGroups",
            "ParameterGroupName",
            "parametergroup",
        ),
    ]

    for service_name, prefix, method, list_key, name_key, resource_type in describe_calls:
        try:
            client = boto3.client(prefix, region_name=region)
            response = getattr(client, method)()
            for item in response.get(list_key, []):
                name = item.get(name_key, "")
                if name.startswith("default"):
                    glob = "default:*" if resource_type == "og" else "default.*"
                    _add(
                        service_name,
                        resource_type,
                        f"arn:aws:{prefix}:*:*:{resource_type}:{glob}",
                        f"AWS-managed default {resource_type} confirmed in account (cannot be tagged)",
                    )
                    break
        except aws_errors:
            continue

    return found
