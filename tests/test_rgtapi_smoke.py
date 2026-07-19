import pytest


def test_rgtapi_module_importable():
    from can_i_tag_aws.resource_groups_api import detect_rgtapi

    assert hasattr(detect_rgtapi, "get_tagging_api_client")


def test_rgtapi_optional_dependency_behavior():
    from can_i_tag_aws.resource_groups_api import detect_rgtapi

    if detect_rgtapi.boto3 is None:
        with pytest.raises(RuntimeError):
            detect_rgtapi.get_tagging_api_client()
