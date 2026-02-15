"""Tests for diff_runs.py comparison logic."""

from pathlib import Path

import pytest

from diff_runs import compare_reports, extract_untaggable_set, parse_args


class TestParseArgs:
    def test_both_positional_args(self):
        args = parse_args(["old.json", "new.json"])
        assert args.old_file == Path("old.json")
        assert args.new_file == Path("new.json")

    def test_no_args_defaults_to_none(self):
        args = parse_args([])
        assert args.old_file is None
        assert args.new_file is None

    def test_one_arg_errors(self):
        with pytest.raises(SystemExit):
            parse_args(["only_one.json"])


class TestExtractUntaggableSet:
    def test_extracts_service_resource_tuples(self):
        report = {
            "untaggable_resources": [
                {"service": "Amazon EC2", "resource": "vpc"},
                {"service": "Amazon S3", "resource": "bucket"},
            ]
        }
        result = extract_untaggable_set(report)
        assert result == {("Amazon EC2", "vpc"), ("Amazon S3", "bucket")}

    def test_returns_empty_set_for_missing_key(self):
        assert extract_untaggable_set({}) == set()

    def test_returns_empty_set_for_empty_list(self):
        assert extract_untaggable_set({"untaggable_resources": []}) == set()


class TestCompareReports:
    def test_detects_added_resources(self):
        old = {"untaggable_resources": [], "summary": {}}
        new = {
            "untaggable_resources": [
                {"service": "Amazon EC2", "resource": "vpc"},
            ],
            "summary": {},
        }
        diff = compare_reports(old, new)
        assert len(diff["added"]) == 1
        assert ("Amazon EC2", "vpc") in diff["added"]
        assert diff["removed"] == []
        assert diff["unchanged_count"] == 0

    def test_detects_removed_resources(self):
        old = {
            "untaggable_resources": [
                {"service": "Amazon EC2", "resource": "vpc"},
            ],
            "summary": {},
        }
        new = {"untaggable_resources": [], "summary": {}}
        diff = compare_reports(old, new)
        assert diff["added"] == []
        assert len(diff["removed"]) == 1
        assert ("Amazon EC2", "vpc") in diff["removed"]

    def test_detects_unchanged_resources(self):
        resources = [
            {"service": "Amazon EC2", "resource": "vpc"},
            {"service": "Amazon S3", "resource": "bucket"},
        ]
        old = {"untaggable_resources": resources, "summary": {}}
        new = {"untaggable_resources": resources, "summary": {}}
        diff = compare_reports(old, new)
        assert diff["added"] == []
        assert diff["removed"] == []
        assert diff["unchanged_count"] == 2

    def test_summary_changes_tracked(self):
        old = {
            "untaggable_resources": [],
            "summary": {
                "total_services": 400,
                "services_without_tagging_api": 100,
                "total_untaggable_resources": 50,
            },
        }
        new = {
            "untaggable_resources": [],
            "summary": {
                "total_services": 410,
                "services_without_tagging_api": 95,
                "total_untaggable_resources": 45,
            },
        }
        diff = compare_reports(old, new)
        assert diff["summary_changes"]["total_services"]["old"] == 400
        assert diff["summary_changes"]["total_services"]["new"] == 410
        assert diff["summary_changes"]["services_without_tagging_api"]["old"] == 100
        assert diff["summary_changes"]["services_without_tagging_api"]["new"] == 95

    def test_missing_summary_defaults_to_zero(self):
        old = {"untaggable_resources": []}
        new = {"untaggable_resources": []}
        diff = compare_reports(old, new)
        assert diff["summary_changes"]["total_services"]["old"] == 0
        assert diff["summary_changes"]["total_services"]["new"] == 0

    def test_mixed_changes(self):
        old = {
            "untaggable_resources": [
                {"service": "A", "resource": "r1"},
                {"service": "B", "resource": "r2"},
            ],
            "summary": {},
        }
        new = {
            "untaggable_resources": [
                {"service": "B", "resource": "r2"},
                {"service": "C", "resource": "r3"},
            ],
            "summary": {},
        }
        diff = compare_reports(old, new)
        assert ("A", "r1") in diff["removed"]
        assert ("C", "r3") in diff["added"]
        assert diff["unchanged_count"] == 1
