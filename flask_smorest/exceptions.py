"""Custom exceptions"""

class FlaskSmorestError(Exception):
    """Generic flask-smorest exception"""


class MissingAPIParameterError(FlaskSmorestError):
    """Missing API parameter"""
