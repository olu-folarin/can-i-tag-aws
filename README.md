# can-i-tag-aws

[![Tests](https://github.com/olu-folarin/can-i-tag-aws/actions/workflows/tests.yml/badge.svg)](https://github.com/olu-folarin/can-i-tag-aws/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/github/license/olu-folarin/can-i-tag-aws)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/olu-folarin/can-i-tag-aws)](https://github.com/olu-folarin/can-i-tag-aws/commits/main)
[![Docker: GHCR](https://img.shields.io/badge/Docker-GHCR-blue?logo=docker)](https://ghcr.io/olu-folarin/can-i-tag-aws)

Automatically detect which AWS resources **cannot be tagged**: so you can build accurate SCP policies and avoid compliance gaps.

## Who Is This For?

- **Platform/Cloud Engineers** writing SCP tagging policies
- **FinOps teams** tracking cost allocation coverage
- **Security/Compliance teams** auditing tagging enforcement
- **Anyone** who's been burned by "tag enforcement broke prod"

## The Problem

Tagging is critical for AWS cost allocation, compliance, and resource management. But not all AWS resources support tagging and AWS doesn't provide a single list of what can't be tagged.

- SCP policies fail when they enforce tags on untaggable resources
- Untagged resources can't be attributed to teams or projects
- You can't enforce compliance on resources you can't tag
- The untaggable list spans 400+ services and changes regularly

For SCP tagging policies, you need to exclude untaggable resources from tag enforcement. That means service-level exclusions (entire services with no tagging API), resource-level exclusions (specific resource types in mixed-support services), and instance-level exclusions (specific AWS-managed default instances of otherwise-taggable resource types). Without these exclusions, your SCP policies will block legitimate API calls.

## The Solution

Parses the **IAM Service Authorization Reference** to identify every AWS resource that cannot be tagged.

### Methodology

A resource is considered **taggable** if:
- It has `aws:ResourceTag/${TagKey}` condition key in the Resource types table, OR
- It's in scope of TagResource/CreateTags/AddTags action

A resource is **untaggable** only if it has NEITHER indicator.

A resource type is **conditionally taggable** if it passes both checks above, but specific AWS-managed default instances within that type cannot be tagged. For example, `elasticache:parametergroup` as a type is taggable. You can tag a user-created parameter group. But `default.redis7` is an AWS-managed default owned by AWS, not by the account, so it will reject tags. This is an instance-level restriction that IAM documentation does not distinguish from user-created instances of the same type. The tool maintains a curated list of known patterns and surfaces them as a separate `conditionally_taggable_resources` category with the ARN patterns you need to exclude from SCP enforcement.

## Why `aws:ResourceTag`?

The `aws:ResourceTag/${TagKey}` condition key is a strong signal that a resource supports tagging in a way that works with tag-based access control. Not all services express this consistently, so detection uses two indicators:

- `aws:ResourceTag/${TagKey}` condition keys in the Resource types table
- Tagging action scope (`TagResource`, `CreateTags`, `AddTags`) from the Actions table

More reliable for governance and SCP strategies than either signal alone.

## Out of Scope

Scope is limited to untaggable resources, not:

- Usage metrics like API requests and bytes processed, which are billing/telemetry aggregates
- Ephemeral items like Lambda invocations and API calls that lack persistent state
- Marketplace and third-party products outside the IAM Service Authorization Reference

## Known Limitations

- **Web scraping dependency**: the tool parses AWS HTML docs; structure changes can break extraction
- **Point-in-time accuracy**: AWS adds/changes services frequently; re-run to stay current
- **Native runs may be unstable on some macOS setups** (Python/lxml segfaults). Docker is the recommended execution path.
- **Conditionally taggable list is manually curated**: AWS does not publish a registry of managed default instances. The `conditionally_taggable_resources` list covers known patterns (ElastiCache default parameter groups, RDS default parameter and option groups, AWS-managed IAM policies) but may be incomplete. If you encounter an AWS-managed resource instance that rejects tags despite the type appearing as taggable, open an issue.

## Quick Start

### Docker (Recommended)

```bash
# Pull and run
docker run --rm -v $(pwd)/output:/app/output ghcr.io/olu-folarin/can-i-tag-aws

# With history tracking
docker run --rm \
  -v $(pwd)/output:/app/output \
  -v $(pwd)/history:/app/history \
  ghcr.io/olu-folarin/can-i-tag-aws
```

### Native Python

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python detect_api_taggable.py
```

For development/testing:

```bash
pip install -r requirements-dev.txt
pytest
```

For optional live validation via Resource Groups Tagging API:

```bash
pip install -r requirements-rgtapi.txt
python resource_groups_api/detect_rgtapi.py
```

Output is saved to `output/` (latest) and `history/` (versioned).

### Sample Output

From `output/api_taggable_resources.json`:

```json
{
  "summary": {
    "total_services": 462,
    "services_without_tagging_api": 125,
    "services_with_tagging_api": 337,
    "mixed_services": 119,
    "total_untaggable_resources": 532,
    "conditionally_taggable_resource_types": 4
  },
  "untaggable_resources": [
    {
      "resource": "execute-api-general",
      "service": "Amazon API Gateway",
      "reason": "service_no_tagging_api"
    }
  ],
  "conditionally_taggable_resources": [
    {
      "resource": "parametergroup",
      "service": "Amazon ElastiCache",
      "arn_pattern": "arn:aws:elasticache:*:*:parametergroup:default.*",
      "description": "AWS-managed default ElastiCache parameter groups (e.g., default.redis7, default.memcached1.6)"
    }
  ],
  "mixed_services_detail": [
    {
      "name": "Amazon ElastiCache",
      "taggable": ["cluster", "subnetgroup", "snapshot"],
      "conditionally_taggable": ["parametergroup"],
      "untaggable": ["globalreplicationgroup"]
    }
  ]
}
```

---

## Scripts

| Script | Role | Description |
|--------|------|-------------|
| `detect_api_taggable.py` | **PRIMARY** | Authoritative resource-level detection (no AWS creds needed) |
| `detect_service_level.py` | SECONDARY | Quick service-level validation |
| `cfn_to_iam_mapper.py` | SUPPLEMENTARY | Maps CloudFormation types to tagging status |
| `diff_runs.py` | UTILITY | Compare two runs to detect changes |
| `resource_groups_api/detect_rgtapi.py` | OPTIONAL | Live validation against your AWS account (requires creds) |

### Script Relationships

```
detect_api_taggable.py (PRIMARY)
│
├── Source: IAM Service Authorization Reference (web scrape)
├── No AWS credentials required
└── Produces: output/api_taggable_resources.json

detect_rgtapi.py (OPTIONAL VALIDATION)
│
├── Source: Your AWS account via Resource Groups Tagging API
├── Requires AWS credentials
└── Use to cross-validate findings in your specific account
```

The primary script works offline by parsing AWS documentation. The RGTAPI script is for optional live validation but only sees resources that exist in your account.

## Output Files

- `output/api_taggable_resources.json`: Comprehensive untaggable resource list
- `output/service_level_untaggable.json`: Services without tagging API
- `history/`: Timestamped versions for change tracking

## Comparing Runs

```bash
python diff_runs.py  # Compare latest two runs
```

## Contributing

PRs and issues welcome. If submitting code:

- Run `ruff check .` and `ruff format --check .` before pushing
- Run `pytest -m "not integration"` to verify unit tests pass
- Add tests for new logic; use `@pytest.mark.integration` for anything hitting live URLs
- One concern per PR

## License

MIT

## References

- [IAM Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/reference.html)
