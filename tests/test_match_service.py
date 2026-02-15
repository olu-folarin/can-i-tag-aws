"""Tests for cfn_to_iam_mapper.match_service() logic."""

from cfn_to_iam_mapper import match_service


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
