"""Crawler content cleaning — XSS sanitization for KB-V4.1-016.

ContentCleaner uses bleach to strip dangerous HTML tags and attributes
from crawled web content before storing it in the knowledge base.
This prevents stored XSS attacks via injected <script>, <iframe>,
javascript: URLs, and other malicious HTML patterns.
"""

import bleach
import logging

logger = logging.getLogger(__name__)

# Allowed HTML tags — safe subset for knowledge base content
ALLOWED_TAGS = [
    "p", "br", "h1", "h2", "h3", "h4", "h5", "h6",
    "ul", "ol", "li", "strong", "em", "a", "blockquote",
    "code", "pre", "table", "thead", "tbody", "tr", "th", "td",
]

# Allowed attributes — only safe, non-executable attributes
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],  # href only allows http/https via ALLOWED_PROTOCOLS
    "td": ["align"],
    "th": ["align"],
}

# Allowed protocols for <a href> — NO javascript:, NO data:
ALLOWED_PROTOCOLS = ["http", "https", "mailto"]

# Maximum content size — KB-V4.1-016 CONTENT-P0-2: reject oversized content
MAX_CONTENT_SIZE = 500_000  # 500KB


class ContentCleaner:
    """Clean crawled HTML content to prevent stored XSS — V4.1 KB-V4.1-016.

    Uses bleach to remove dangerous tags (<script>, <iframe>, <object>, <embed>,
    <style>) and attributes (onclick, onload, onerror, etc.), then strips
    javascript: protocol from <a> href attributes.
    """

    def clean(self, raw_html: str) -> str:
        """Bleach-clean HTML content, removing dangerous tags and attributes.

        Args:
            raw_html: Raw HTML content extracted from the crawled page.

        Returns:
            Cleaned HTML with only safe tags and attributes preserved.

        Raises:
            ValueError: If content exceeds MAX_CONTENT_SIZE bytes.
        """
        if len(raw_html) > MAX_CONTENT_SIZE:
            logger.warning("Content exceeds max size: %d > %d bytes", len(raw_html), MAX_CONTENT_SIZE)
            raise ValueError(
                f"Content exceeds maximum size of {MAX_CONTENT_SIZE} bytes "
                f"({len(raw_html)} bytes received)."
            )

        cleaned = bleach.clean(
            raw_html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            protocols=ALLOWED_PROTOCOLS,
            strip=True,  # Strip disallowed tags completely (not just escape)
        )

        logger.debug(
            "Content cleaned: %d → %d bytes (%d%% reduction)",
            len(raw_html), len(cleaned),
            int((1 - len(cleaned) / max(len(raw_html), 1)) * 100),
        )

        return cleaned

    def extract_text(self, html_content: str) -> str:
        """Extract plain text from HTML, stripping all tags.

        Used for embedding when HTML markup is not needed in the chunk.
        """
        return bleach.clean(html_content, tags=[], strip=True)
