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

# AWS-managed default resource instances (parameter groups, option groups,
# AWS-managed IAM policies, and similar) are no longer hardcoded here. They are
# derived dynamically from scraped ARN templates and stable naming conventions,
# with optional live confirmation via boto3. See managed_defaults.py.
