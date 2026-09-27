from enum import Enum


class CommentStatus(str, Enum):
    """
    Explicit status model for public comments availability and accessibility.

    Statuses:
    - AVAILABLE: Public comments are present and successfully extractable.
    - NONE_PRESENT: Page loaded normally and explicitly indicates zero public comments.
    - DISABLED: Comments feature has been explicitly disabled for this article.
    - LOGIN_REQUIRED: Comment section is hidden behind user authentication/login.
    - NOT_LOADED: Comment section exists but failed to dynamically load/render in DOM.
    - BLOCKED: Access was blocked by site protection, CAPTCHA, or rate limit.
    - UNSUPPORTED: Source platform does not support public comment extraction.
    - UNKNOWN: Status could not be conclusively determined from diagnostic inspection.
    - EXTRACTION_ERROR: Comments feature detected but parsing/extraction encountered error.
    """
    AVAILABLE = "AVAILABLE"
    NONE_PRESENT = "NONE_PRESENT"
    DISABLED = "DISABLED"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    NOT_LOADED = "NOT_LOADED"
    BLOCKED = "BLOCKED"
    UNSUPPORTED = "UNSUPPORTED"
    UNKNOWN = "UNKNOWN"
    EXTRACTION_ERROR = "EXTRACTION_ERROR"
