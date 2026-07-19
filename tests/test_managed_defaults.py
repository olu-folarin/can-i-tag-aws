"""Tests for the dynamic AWS-managed-defaults detection engine."""

from managed_defaults import (
    RULES,
    build_arn_pattern,
    build_conditionally_taggable,
    detect_conditionally_taggable,
    merge_conditionally_taggable,
)


def _rule(name: str):
    return next(r for r in RULES if r.name == name)


class TestBuildArnPattern:
    def test_parameter_group_template_from_docs(self):
        template = "arn:${Partition}:elasticache:${Region}:${Account}:parametergroup:${CacheParameterGroupName}"
        pattern = build_arn_pattern(template, _rule("parameter_group_default"))
        assert pattern == "arn:aws:elasticache:*:*:parametergroup:default.*"

    def test_option_group_template_uses_colon_glob(self):
        template = "arn:${Partition}:rds:${Region}:${Account}:og:${OptionGroupName}"
        pattern = build_arn_pattern(template, _rule("option_group_default"))
        assert pattern == "arn:aws:rds:*:*:og:default:*"

    def test_iam_policy_template_pins_account_to_aws(self):
        template = "arn:${Partition}:iam::${Account}:policy/${PolicyNameWithPath}"
        pattern = build_arn_pattern(template, _rule("aws_managed_iam_policy"))
        assert pattern == "arn:aws:iam::aws:policy/*"

    def test_slash_delimiter_is_preserved(self):
        template = "arn:${Partition}:memorydb:${Region}:${Account}:parametergroup/${ParameterGroupName}"
        pattern = build_arn_pattern(template, _rule("parameter_group_default"))
        assert pattern == "arn:aws:memorydb:*:*:parametergroup/default.*"


class TestDetectConditionallyTaggable:
    def test_flags_parameter_group(self):
        arn_templates = {
            "parametergroup": "arn:${Partition}:elasticache:${Region}:${Account}:parametergroup:${Name}",
            "cluster": "arn:${Partition}:elasticache:${Region}:${Account}:cluster:${Name}",
        }
        out = detect_conditionally_taggable(
            "Amazon ElastiCache", "elasticache", ["parametergroup", "cluster"], arn_templates
        )
        assert [e["resource"] for e in out] == ["parametergroup"]
        assert out[0]["arn_pattern"].endswith("parametergroup:default.*")
        assert out[0]["source"] == "heuristic"

    def test_flags_rds_pg_and_og(self):
        arn_templates = {
            "pg": "arn:${Partition}:rds:${Region}:${Account}:pg:${Name}",
            "og": "arn:${Partition}:rds:${Region}:${Account}:og:${Name}",
        }
        out = detect_conditionally_taggable("Amazon RDS", "rds", ["pg", "og"], arn_templates)
        by_resource = {e["resource"]: e["arn_pattern"] for e in out}
        assert by_resource["pg"] == "arn:aws:rds:*:*:pg:default.*"
        assert by_resource["og"] == "arn:aws:rds:*:*:og:default:*"

    def test_only_exact_iam_policy_matches(self):
        # "scheduling-policy", "ipam-policy" etc. must NOT be treated as managed policies.
        out = detect_conditionally_taggable("Amazon EC2", "ec2", ["ipam-policy", "verified-access-policy"], {})
        assert out == []

    def test_iam_policy_matches(self):
        out = detect_conditionally_taggable("AWS Identity and Access Management (IAM)", "iam", ["policy", "role"], {})
        assert [e["resource"] for e in out] == ["policy"]
        assert out[0]["arn_pattern"] == "arn:aws:iam::aws:policy/*"

    def test_fallback_pattern_when_template_missing(self):
        out = detect_conditionally_taggable("Amazon Redshift", "redshift", ["parametergroup"], {})
        assert out[0]["arn_pattern"] == "arn:aws:redshift:*:*:parametergroup:default.*"

    def test_non_matching_service_returns_empty(self):
        out = detect_conditionally_taggable("Amazon S3", "s3", ["bucket", "object"], {})
        assert out == []


class TestBuildAndMerge:
    def test_build_across_services(self):
        has_tagging_api = [
            {
                "name": "Amazon ElastiCache",
                "service_prefix": "elasticache",
                "taggable_resources": ["parametergroup", "cluster"],
                "arn_templates": {},
            },
            {
                "name": "Amazon S3",
                "service_prefix": "s3",
                "taggable_resources": ["bucket"],
                "arn_templates": {},
            },
        ]
        out = build_conditionally_taggable(has_tagging_api)
        assert [e["service"] for e in out] == ["Amazon ElastiCache"]

    def test_live_overrides_heuristic_on_overlap(self):
        heuristic = [
            {
                "resource": "pg",
                "service": "Amazon RDS",
                "arn_pattern": "arn:aws:rds:*:*:pg:default.*",
                "description": "heuristic",
                "source": "heuristic",
            }
        ]
        live = [
            {
                "resource": "pg",
                "service": "Amazon RDS",
                "arn_pattern": "arn:aws:rds:*:*:pg:default.*",
                "description": "live",
                "source": "live",
            }
        ]
        merged = merge_conditionally_taggable(heuristic, live)
        assert len(merged) == 1
        assert merged[0]["source"] == "live"

    def test_merge_keeps_distinct_entries(self):
        heuristic = [
            {
                "resource": "pg",
                "service": "Amazon RDS",
                "arn_pattern": "arn:aws:rds:*:*:pg:default.*",
                "description": "h",
                "source": "heuristic",
            }
        ]
        live = [
            {
                "resource": "policy",
                "service": "AWS Identity and Access Management (IAM)",
                "arn_pattern": "arn:aws:iam::aws:policy/*",
                "description": "l",
                "source": "live",
            }
        ]
        merged = merge_conditionally_taggable(heuristic, live)
        assert len(merged) == 2
