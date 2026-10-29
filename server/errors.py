"""Shared API errors for imported modules and python -m server.app."""
class ApiError(Exception):
    def __init__(self, status, message, code=0):
        self.status, self.message, self.code = status, message, code
