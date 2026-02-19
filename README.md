# can-i-tag-aws

Automatically detect which AWS resources **cannot be tagged**: so you can build accurate SCP policies and avoid compliance gaps.

## Who Is This For?

- **Platform/Cloud Engineers** writing SCP tagging policies
- **FinOps teams** tracking cost allocation coverage
- **Security/Compliance teams** auditing tagging enforcement
- **Anyone** who's been burned by "tag enforcement broke prod"

## The Problem

**Tagging is critical for AWS cost allocation, compliance, and resource management.** But not all AWS resources support tagging and AWS doesn't provide a single list of what can't be tagged.

This creates real problems:
- **SCP policies fail** when they enforce tags on untaggable resources
- **Cost allocation gaps**: untagged resources can't be attributed to teams/projects
- **Compliance blind spots**: you can't enforce what you can't tag
- **Manual maintenance**: hundreds of untaggable resources across 400+ services

## The Solution

This tool automatically detects all AWS resources that cannot be tagged by parsing the authoritative source: the **IAM Service Authorization Reference**.

### Methodology

A resource is considered **taggable** if:
- It has `aws:ResourceTag/${TagKey}` condition key in the Resource types table, OR
- It's in scope of TagResource/CreateTags/AddTags action

A resource is **untaggable** only if it has NEITHER indicator.

Run the tool to get current findings for your analysis.

## Why `aws:ResourceTag`?

This tool checks for `aws:ResourceTag/${TagKey}` condition key presence as a strong signal that a resource supports tagging in a way that works with tag-based access control.

However, not all services express tagging support consistently, so the tool uses **two indicators**:

- **`aws:ResourceTag/${TagKey}` condition keys** in the Resource types table
- **Tagging action scope** (for example `TagResource`, `CreateTags`, `AddTags`) from the Actions table

This makes the results more useful for real-world governance (including SCP strategies) than relying on only one signal.

## Out of Scope

This tool detects **untaggable resources**, not:

- **Usage metrics** (API requests, bytes processed): billing/telemetry aggregates, not resources
- **Ephemeral items** (Lambda invocations, API calls): transient actions without persistent state
- **Marketplace/third-party products**: not covered by the IAM Service Authorization Reference

## Known Limitations

- **Web scraping dependency**: the tool parses AWS HTML docs; structure changes can break extraction
- **Point-in-time accuracy**: AWS adds/changes services frequently; re-run to stay current
- **Native runs may be unstable on some macOS setups** (Python/lxml segfaults). Docker is the recommended execution path.

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

## Why This Matters

For SCP tagging policies, you need to **exclude untaggable resources** from tag enforcement:

1. **Service-level exclusions**: Entire services with no tagging API
2. **Resource-level exclusions**: Specific resources in mixed-support services

Without these exclusions, your SCP policies will block legitimate resource creation.

## Contributing

Contributions welcome! Please open an issue or PR.

## License

MIT

## References

- [IAM Service Authorization Reference](https://docs.aws.amazon.com/service-authorization/latest/reference/reference.html)
