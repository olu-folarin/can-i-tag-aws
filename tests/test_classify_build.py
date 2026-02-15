"""Tests for classify_results() and build_report() in detect_api_taggable and detect_service_level."""

from detect_api_taggable import build_report as api_build_report
from detect_api_taggable import classify_results as api_classify
from detect_service_level import build_report as svc_build_report
from detect_service_level import classify_results as svc_classify


class TestApiClassifyResults:
    def test_separates_errors(self):
        results = [{"name": "svc1", "error": "timeout"}]
        no_tag, has_tag, mixed, errors = api_classify(results)
        assert len(errors) == 1
        assert no_tag == []
        assert has_tag == []
        assert mixed == []

    def test_separates_no_tagging_api(self):
        results = [{"name": "svc1", "has_tagging_api": False, "all_resources": ["r1"]}]
        no_tag, has_tag, mixed, errors = api_classify(results)
        assert len(no_tag) == 1
        assert has_tag == []

    def test_separates_has_tagging_api(self):
        results = [
            {
                "name": "svc1",
                "has_tagging_api": True,
                "untaggable_resources": [],
                "taggable_resources": ["r1"],
            }
        ]
        no_tag, has_tag, mixed, errors = api_classify(results)
        assert len(has_tag) == 1
        assert mixed == []

    def test_identifies_mixed_services(self):
        results = [
            {
                "name": "svc1",
                "has_tagging_api": True,
                "untaggable_resources": ["r2"],
                "taggable_resources": ["r1"],
            }
        ]
        no_tag, has_tag, mixed, errors = api_classify(results)
        assert len(has_tag) == 1
        assert len(mixed) == 1

    def test_empty_results(self):
        no_tag, has_tag, mixed, errors = api_classify([])
        assert no_tag == has_tag == mixed == errors == []


class TestApiBuildReport:
    def test_builds_summary(self):
        services = [{"name": "s1"}, {"name": "s2"}, {"name": "s3"}]
        no_tag = [{"name": "s1", "all_resources": ["r1", "r2"]}]
        has_tag = [{"name": "s2"}, {"name": "s3"}]
        mixed = [{"name": "s3", "untaggable_resources": ["r3"], "taggable_resources": ["r4"]}]

        report = api_build_report(services, no_tag, has_tag, mixed)

        assert report["summary"]["total_services"] == 3
        assert report["summary"]["services_without_tagging_api"] == 1
        assert report["summary"]["services_with_tagging_api"] == 2
        assert report["summary"]["mixed_services"] == 1
        assert report["summary"]["total_untaggable_resources"] == 3

    def test_untaggable_resources_have_reasons(self):
        no_tag = [{"name": "NoTag", "all_resources": ["res1"]}]
        mixed = [{"name": "Mixed", "untaggable_resources": ["res2"], "taggable_resources": []}]

        report = api_build_report([], no_tag, [], mixed)

        reasons = {r["reason"] for r in report["untaggable_resources"]}
        assert "service_no_tagging_api" in reasons
        assert "resource_not_in_tag_action_scope" in reasons

    def test_empty_inputs(self):
        report = api_build_report([], [], [], [])
        assert report["summary"]["total_untaggable_resources"] == 0
        assert report["untaggable_resources"] == []


class TestSvcClassifyResults:
    def test_classifies_by_tagging_info(self):
        services = [
            {"name": "A", "tagging_info": {"has_tagging": True}},
            {"name": "B", "tagging_info": {"has_tagging": False}},
            {"name": "C", "tagging_info": {"error": "timeout"}},
        ]
        taggable, untaggable, errors = svc_classify(services)
        assert len(taggable) == 1
        assert len(untaggable) == 1
        assert len(errors) == 1

    def test_empty_services(self):
        taggable, untaggable, errors = svc_classify([])
        assert taggable == untaggable == errors == []


class TestSvcBuildReport:
    def test_builds_report_structure(self):
        services = [{"name": "A"}, {"name": "B"}]
        taggable = [{"name": "A", "tagging_info": {"tagging_actions": ["TagResource"]}}]
        untaggable = [{"name": "B", "url": "https://example.com"}]

        report = svc_build_report(services, taggable, untaggable, [])

        assert report["summary"]["total_services"] == 2
        assert report["summary"]["taggable_services"] == 1
        assert report["summary"]["untaggable_services"] == 1
        assert "B" in report["untaggable_services"]
        assert "A" in report["taggable_services"]
