"""Structured tool errors returned to the planner instead of raised to the user."""


class ToolError(ValueError):
    def __init__(self, code: str, message: str, recoverable: bool = False):
        super().__init__(message)
        self.code, self.recoverable = code, recoverable
