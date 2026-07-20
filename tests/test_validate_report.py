"""Tests for the report validation gate."""

import copy

from can_i_tag_aws.validate_report import assess_delta, check_invariants


def _good_report() -> dict:
    """A minimal report that satisfies every hard invariant."""
    return {
        "summary": {
            "total_services": 470,
            "services_with_tagging_api": 340,
            "total_untaggable_resources": 500,
            "conditionally_taggable_resource_types": 7,
        },
        "services_without_tagging_api": ["AWS Health (health)"],
        "untaggable_resources": [
            {"resource": "certificateid", "service": "Amazon WorkSpaces (workspaces)", "reason": "x"},
        ],
        "conditionally_taggable_resources": [
            {
                "resource": "parametergroup",
                "service": "Amazon ElastiCache (elasticache)",
                "arn_pattern": "arn:aws:elasticache:*:*:parametergroup:default.*",
                "description": "x",
                "source": "heuristic",
            },
        ],
        "mixed_services_detail": [
            {"name": "Amazon EC2 (ec2)", "taggable": ["instance"], "conditionally_taggable": [], "untaggable": ["x"]},
            {"name": "Amazon S3 (s3)", "taggable": ["bucket"], "conditionally_taggable": [], "untaggable": ["y"]},
        ],
    }


class TestCheckInvariants:
    def test_good_report_passes(self):
        assert check_invariants(_good_report()) == []

    def test_too_few_services(self):
        r = _good_report()
        r["summary"]["total_services"] = 100
        assert any("total_services" in v for v in check_invariants(r))

    def test_too_few_tagging_services(self):
        r = _good_report()
        r["summary"]["services_with_tagging_api"] = 10
        assert any("services_with_tagging_api" in v for v in check_invariants(r))

    def test_untaggable_collapse(self):
        r = _good_report()
        r["summary"]["total_untaggable_resources"] = 50
        assert any("total_untaggable_resources" in v for v in check_invariants(r))

    def test_untaggable_balloon(self):
        r = _good_report()
        r["summary"]["total_untaggable_resources"] = 2000
        assert any("total_untaggable_resources" in v for v in check_invariants(r))

    def test_conditionally_taggable_floor(self):
        r = _good_report()
        r["summary"]["conditionally_taggable_resource_types"] = 2
        assert any("conditionally_taggable_resource_types" in v for v in check_invariants(r))

    def test_missing_ec2_anchor(self):
        r = _good_report()
        r["mixed_services_detail"] = [r["mixed_services_detail"][1]]  # drop EC2, keep S3
        assert any("EC2" in v for v in check_invariants(r))

    def test_ec2_instance_flipped_untaggable(self):
        r = _good_report()
        r["untaggable_resources"].append({"resource": "instance", "service": "Amazon EC2 (ec2)", "reason": "x"})
        assert any("instance" in v for v in check_invariants(r))

    def test_missing_elasticache_conditional_anchor(self):
        r = _good_report()
        r["conditionally_taggable_resources"] = []
        assert any("ElastiCache" in v for v in check_invariants(r))


class TestAssessDelta:
    def _report_with(self, pairs: list[tuple[str, str]]) -> dict:
        return {"untaggable_resources": [{"service": s, "resource": r} for s, r in pairs]}

    def test_no_previous_run(self):
        churn, needs_review = assess_delta(None, self._report_with([("a", "1")]))
        assert churn == 0.0
        assert needs_review is False

    def test_identical_runs(self):
        pairs = [("a", "1"), ("b", "2"), ("c", "3"), ("d", "4")]
        prev = self._report_with(pairs)
        churn, needs_review = assess_delta(prev, copy.deepcopy(prev))
        assert churn == 0.0
        assert needs_review is False

    def test_small_change_no_review(self):
        prev = self._report_with([("a", str(i)) for i in range(10)])
        curr = self._report_with([("a", str(i)) for i in range(10)] + [("a", "new")])
        churn, needs_review = assess_delta(prev, curr)
        assert churn <= 0.25
        assert needs_review is False

    def test_large_change_needs_review(self):
        prev = self._report_with([("a", str(i)) for i in range(10)])
        curr = self._report_with([("a", str(i)) for i in range(3)])  # dropped 7 of 10
        churn, needs_review = assess_delta(prev, curr)
        assert churn > 0.25
        assert needs_review is True
