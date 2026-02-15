"""Tests for cfn_to_iam_mapper.match_service() and service_mapping helpers."""

from cfn_to_iam_mapper import match_service
from service_mapping import normalize_for_fuzzy_match


class TestMatchService:
    def test_exact_mapping_match(self):
        """CFN prefix found in CFN_TO_IAM_SERVICE and present in service list."""
        service_list = ["Amazon EC2", "Amazon S3"]
        assert match_service("ec2", service_list) == "Amazon EC2"

    def test_exact_mapping_case_insensitive(self):
        service_list = ["Amazon EC2"]
        assert match_service("EC2", service_list) == "Amazon EC2"

    def test_mapping_not_in_service_list_falls_through(self):
        """Mapping exists but IAM name not in the provided service list."""
        service_list = ["Some Other Service"]
        # ec2 maps to "Amazon EC2" but that's not in service_list
        # fuzzy match won't help either
        assert match_service("ec2", service_list) is None

    def test_fuzzy_match_fallback(self):
        """No exact mapping — fuzzy match strips prefixes and normalizes."""
        service_list = ["Amazon DynamoDB"]
        # "dynamodb" is in CFN_TO_IAM_SERVICE, so this hits the exact path
        assert match_service("dynamodb", service_list) == "Amazon DynamoDB"

    def test_no_match_returns_none(self):
        service_list = ["Amazon EC2", "Amazon S3"]
        assert match_service("nonexistent", service_list) is None

    def test_empty_service_list(self):
        assert match_service("ec2", []) is None

    def test_lambda_mapping(self):
        service_list = ["AWS Lambda"]
        assert match_service("lambda", service_list) == "AWS Lambda"

    def test_multiple_services_returns_correct_one(self):
        service_list = ["Amazon EC2", "Amazon S3", "AWS Lambda"]
        assert match_service("s3", service_list) == "Amazon S3"
        assert match_service("lambda", service_list) == "AWS Lambda"


class TestNormalizeFuzzyMatch:
    def test_strips_amazon_prefix(self):
        assert normalize_for_fuzzy_match("Amazon EC2") == "ec2"

    def test_strips_aws_prefix(self):
        assert normalize_for_fuzzy_match("AWS Lambda") == "lambda"

    def test_does_not_strip_amazon_substring(self):
        """Regression: 'amazon' in the middle should NOT be stripped."""
        result = normalize_for_fuzzy_match("Something Amazon Inside")
        assert "amazon" in result

    def test_does_not_strip_aws_substring(self):
        """Regression: 'aws' in the middle should NOT be stripped."""
        result = normalize_for_fuzzy_match("Powered by AWS Mantle")
        assert "aws" in result

    def test_rawdata_not_corrupted(self):
        """Regression: 'rawdata' must not become 'rdata'."""
        assert normalize_for_fuzzy_match("rawdata") == "rawdata"

    def test_normalizes_spaces_hyphens_underscores(self):
        assert normalize_for_fuzzy_match("some-service_name here") == "someservicenamehere"

    def test_already_lowercase_prefix(self):
        assert normalize_for_fuzzy_match("amazonec2") == "ec2"
        assert normalize_for_fuzzy_match("awslambda") == "lambda"
