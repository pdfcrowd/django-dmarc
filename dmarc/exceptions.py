from django.core.management.base import CommandError


class InvalidDMARCReport(CommandError):
    """The report contains invalid input and cannot be imported unchanged."""
