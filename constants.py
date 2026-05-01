"""Shared constants for AWS documentation scraping and analysis."""

# AWS IAM Service Authorization Reference
SERVICE_AUTH_REF_BASE = "https://docs.aws.amazon.com/service-authorization/latest/reference"
SERVICE_AUTH_REF_TOC = f"{SERVICE_AUTH_REF_BASE}/reference_policies_actions-resources-contextkeys.html"

# CloudFormation Resource Specification
CFN_SPEC_URL = "https://d1uauaxba7bl26.cloudfront.net/latest/gzip/CloudFormationResourceSpecification.json"

# Scraping thresholds
MIN_EXPECTED_SERVICES = 400

# HTTP settings
DEFAULT_HTTP_TIMEOUT = 30
MAX_RETRIES = 3
RETRY_DELAY = 2

# Tagging action patterns used to identify tagging support in IAM docs
TAGGING_ACTION_PATTERNS = [
    "tagresource",
    "untagresource",
    "createtags",
    "deletetags",
    "addtags",
    "removetags",
]

# AWS-managed default resource instances within otherwise-taggable resource types.
# The resource TYPE supports tagging, but these specific AWS-managed instances are
# read-only to the account holder and will reject user-defined tags.
# SCP tag enforcement policies must exclude these ARN patterns to avoid blocking
# legitimate API calls that reference these defaults.
#
# Note: this list requires manual curation as AWS does not publish a comprehensive
# registry of managed defaults. Additions should be validated empirically.
AWS_MANAGED_DEFAULTS: list[dict] = [
    {
        "service": "Amazon ElastiCache",
        "resource_type": "parametergroup",
        "arn_pattern": "arn:aws:elasticache:*:*:parametergroup:default.*",
        "description": "AWS-managed default ElastiCache parameter groups (e.g., default.redis7, default.memcached1.6)",
    },
    {
        "service": "Amazon RDS",
        "resource_type": "pg",
        "arn_pattern": "arn:aws:rds:*:*:pg:default.*",
        "description": "AWS-managed default RDS parameter groups (e.g., default.mysql8.0, default.postgres15)",
    },
    {
        "service": "Amazon RDS",
        "resource_type": "og",
        "arn_pattern": "arn:aws:rds:*:*:og:default:*",
        "description": "AWS-managed default RDS option groups (e.g., default:mysql-8-0, default:postgres-15)",
    },
    {
        "service": "AWS Identity and Access Management (IAM)",
        "resource_type": "policy",
        "arn_pattern": "arn:aws:iam::aws:policy/*",
        "description": "AWS-managed IAM policies (e.g., arn:aws:iam::aws:policy/ReadOnlyAccess)",
    },
]
