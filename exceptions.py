"""Custom exceptions for AWS documentation parsing errors."""


class AWSDocParsingError(Exception):
    """Base exception for AWS documentation parsing errors."""

    pass


class AWSDocStructureError(AWSDocParsingError):
    """Raised when AWS documentation structure has changed unexpectedly."""

    pass
