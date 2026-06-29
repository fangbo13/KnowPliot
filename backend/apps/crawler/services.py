"""Crawler service — orchestrate URL crawl with SSRF/XSS protections.

V4.2 SYS-V4.2-002: Added DNS rebinding re-validation before httpx fetch.
V4.2 SYS-V4.2-003: Now validates ALL intermediate redirect IPs (response.history).
V4.2 SYS-V4.2-005: RobotsTxtChecker now validates robots.txt URL IPs before fetching.

CrawlerService: Full crawl workflow (validate → re-validate DNS → robots → fetch → clean → hash).
RobotsTxtChecker: Pre-fetch robots.txt, parse Disallow rules, respect Crawl-delay.
"""

import hashlib
import httpx
import logging
import socket
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from django.conf import settings
from django.core.cache import cache

from .validators import (
    CrawlURLValidator,
    MAX_REDIRECTS,
    _is_private_ip,
    _validate_hostname_ips,
)
from .cleaners import ContentCleaner

logger = logging.getLogger(__name__)

# User-Agent string — identifies the crawler to target sites
CRAWL_USER_AGENT = getattr(
    settings, "CRAWL_USER_AGENT",
    "EY-Onboarding-AI-Crawler/1.0 (+https://ey.com/bot)",
)

# Robots.txt cache TTL — 24 hours
ROBOTS_CACHE_TTL = 86400


class RobotsTxtChecker:
    """Check robots.txt compliance before crawling — V4.1 KB-V4.1-014.

    V4.2 SYS-V4.2-005: Added IP validation for robots.txt prefetch URL.
    The prefetch itself is an SSRF vector, so we validate the resolved IPs
    before sending the HTTP request.

    Fetches https://{domain}/robots.txt, parses Disallow rules,
    and respects Crawl-delay directives. Results are cached for 24 hours
    to avoid repeated fetching of the same robots.txt.
    """

    def __init__(self):
        self.url_validator = CrawlURLValidator()

    def can_fetch(self, url: str, user_agent: str = CRAWL_USER_AGENT) -> tuple[bool, float]:
        """Check if the given URL is allowed by the site's robots.txt.

        V4.2 SYS-V4.2-005: Validates robots.txt URL IPs before fetching.
        If the robots.txt domain resolves to a private IP, the prefetch
        is blocked and the crawl is rejected (conservative: deny by default).

        Returns (is_allowed, crawl_delay_seconds) tuple.
        """
        parsed = urlparse(url)
        domain = parsed.hostname
        if not domain:
            return False, 0

        robots_url = f"https://{domain}/robots.txt"

        # V4.2 SYS-V4.2-005: Validate robots.txt URL IPs before fetching
        # This prevents SSRF via robots.txt prefetch (DNS rebinding vector)
        is_valid, reason = self.url_validator.validate_robots_txt_url(robots_url)
        if not is_valid:
            logger.warning(
                "robots.txt prefetch blocked for %s: %s — denying crawl by default",
                url, reason,
            )
            return False, 0  # Conservative: if robots.txt is unsafe, deny the crawl

        # Try cache first
        cache_key = f"robots_txt:{domain}"
        cached = cache.get(cache_key)
        if cached is not None:
            rp = cached
        else:
            rp = RobotFileParser()
            rp.set_url(robots_url)
            try:
                rp.read()
                cache.set(cache_key, rp, ROBOTS_CACHE_TTL)
                logger.info("Fetched and cached robots.txt for %s", domain)
            except Exception as exc:
                logger.warning("Could not fetch robots.txt for %s: %s", domain, exc)
                # If robots.txt is unreachable, default to allowing
                # (conservative approach: be permissive when robots.txt is absent)
                return True, 0

        is_allowed = rp.can_fetch(user_agent, url)
        crawl_delay = rp.crawl_delay(user_agent) or 0.0

        if not is_allowed:
            logger.info("robots.txt DISALLOW: %s by %s", url, user_agent)

        return is_allowed, float(crawl_delay)


class CrawlerService:
    """Orchestrate web content crawling with security protections.

    V4.2 enhancements:
    - SYS-V4.2-002: DNS rebinding re-validation before httpx fetch
    - SYS-V4.2-003: Validates ALL redirect chain IPs (not just final)
    - SYS-V4.2-005: RobotsTxtChecker validates robots.txt URL IPs

    Full crawl workflow:
    1. Validate URL (SSRF protection via CrawlURLValidator)
    2. Re-validate DNS (DNS rebinding defense — time-of-use check)
    3. Check robots.txt compliance (with SSRF protection)
    4. Fetch content via httpx (with timeout and redirect limits)
    5. Verify content type (reject non-text responses)
    6. Check ALL redirect IPs (DNS rebinding + intermediate node defense)
    7. Extract content via trafilatura
    8. Clean content via bleach ContentCleaner
    9. Hash content for dedup detection
    """

    def __init__(self):
        self.url_validator = CrawlURLValidator()
        self.content_cleaner = ContentCleaner()
        self.robots_checker = RobotsTxtChecker()

    async def crawl_url(self, url: str) -> dict:
        """Full crawl workflow: validate → re-validate → fetch → clean → extract → hash.

        Args:
            url: The URL to crawl.

        Returns:
            Dict with extracted_text, title, content_hash, final_url,
            redirect_count, raw_content_size, cleaned_content_size.

        Raises:
            ValueError: If URL validation fails, content type is wrong,
                        or DNS rebinding is detected.
        """
        # Step 1: URL validation (SSRF protection)
        is_valid, reason = self.url_validator.validate(url)
        if not is_valid:
            raise ValueError(f"URL validation failed: {reason}")

        # V4.2 SYS-V4.2-002: DNS rebinding re-validation — time-of-use check
        # Between initial validation (time-of-check) and actual fetch (time-of-use),
        # DNS may have been rebinded. Re-resolve and validate before httpx request.
        parsed = urlparse(url)
        hostname = parsed.hostname
        if hostname:
            is_public, dns_reason = _validate_hostname_ips(hostname)
            if not is_public:
                raise ValueError(
                    f"DNS rebinding detected: hostname '{hostname}' "
                    f"resolved to private IP at fetch time — {dns_reason}"
                )

        # Step 2: robots.txt compliance (V4.2 SYS-V4.2-005: with SSRF protection)
        is_allowed, crawl_delay = self.robots_checker.can_fetch(url)
        if not is_allowed:
            raise ValueError(f"robots.txt disallows crawling: {url}")
        if crawl_delay > 0:
            logger.info("Respecting Crawl-delay of %.1f seconds for %s", crawl_delay, url)
            time.sleep(crawl_delay)

        # Step 3: Fetch content via httpx
        client = httpx.AsyncClient(
            verify=True,
            timeout=httpx.Timeout(connect=5.0, read=30.0, write=10.0, pool=5.0),
            follow_redirects=True,
            max_redirects=MAX_REDIRECTS,
            headers={"User-Agent": CRAWL_USER_AGENT},
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
        )

        try:
            response = await client.get(url)
        except httpx.TimeoutException:
            raise ValueError(f"Timeout fetching URL: {url}")
        except httpx.RequestError as exc:
            raise ValueError(f"Network error fetching URL: {exc}")
        finally:
            await client.aclose()

        # Step 4: Verify response status
        if response.status_code != 200:
            raise ValueError(f"HTTP {response.status_code} response from {url}")

        # Step 5: Verify content type (reject non-text)
        content_type = response.headers.get("content-type", "")
        allowed_content_types = ["text/html", "text/plain", "application/xhtml+xml"]
        if not any(ct in content_type for ct in allowed_content_types):
            raise ValueError(f"Non-text content type: {content_type}")

        # V4.2 SYS-V4.2-003: Validate ALL redirect chain IPs
        # Previous: only checked final IP. Now checks response.history + final.
        # This prevents redirect chains with private IPs in intermediate nodes.
        is_valid_chain, chain_reason = self.url_validator.validate_redirect_chain(response)
        if not is_valid_chain:
            raise ValueError(f"Redirect chain validation failed: {chain_reason}")

        # Step 7: Extract content via trafilatura
        import trafilatura

        extracted = trafilatura.extract(response.text)
        if not extracted:
            raise ValueError("Could not extract text content from page.")

        # Get metadata (title, author, date)
        metadata = trafilatura.extract(response.text, output_format="json")
        title = ""
        if metadata:
            import json
            try:
                meta_data = json.loads(metadata)
                title = meta_data.get("title", "")
            except json.JSONDecodeError:
                pass
        if not title:
            title = url.split("/")[-1] or urlparse(url).hostname or url[:80]

        # Step 8: Content cleaning (XSS prevention)
        cleaned_text = self.content_cleaner.clean(extracted)

        # Step 9: Content hash (dedup preparation)
        content_hash = hashlib.sha256(cleaned_text.encode("utf-8")).hexdigest()

        # Build result
        redirect_count = len(response.history)

        return {
            "extracted_text": cleaned_text,
            "title": title,
            "content_hash": content_hash,
            "final_url": str(response.url),
            "redirect_count": redirect_count,
            "raw_content_size": len(response.text),
            "cleaned_content_size": len(cleaned_text),
        }
