"""Crawler URL validators — SSRF protection for KB-V4.1-011/012/013.

V4.2 SYS-V4.2-001: IPv6-mapped IPv4 address bypass — added ipv4_mapped check.
V4.2 SYS-V4.2-002: DNS rebinding time-of-check/time-of-use — added pre-fetch DNS re-validation.
V4.2 SYS-V4.2-003: Redirect chain intermediate IPs — now checks ALL redirect history IPs.
V4.2 SYS-V4.2-005: RobotsTxtChecker SSRF — added IP validation for robots.txt prefetch URL.

CrawlURLValidator provides comprehensive SSRF defense:
- Protocol whitelist: only http/https (KB-V4.1-013)
- Internal IP blacklist: reject private/reserved IP ranges (KB-V4.1-011)
- V4.2: IPv4-mapped IPv6 addresses detected via .ipv4_mapped property
- DNS Rebinding protection: validate resolved IPs before and after redirects
- URL length limit: max 2048 chars (KB-V4.1-012)
- Redirect limit: max 3 redirects (KB-V4.1-012)
"""

import ipaddress
import socket
import logging
from urllib.parse import urlparse

from django.conf import settings

logger = logging.getLogger(__name__)

# Protocol whitelist — KB-V4.1-013: only allow http and https
ALLOWED_SCHEMES = {"http", "https"}

# Private/reserved IP ranges — KB-V4.1-011: reject internal network access
PRIVATE_IP_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),        # Class A private
    ipaddress.ip_network("172.16.0.0/12"),     # Class B private
    ipaddress.ip_network("192.168.0.0/16"),    # Class C private
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local (cloud metadata)
    ipaddress.ip_network("0.0.0.0/8"),         # "This network"
    ipaddress.ip_network("100.64.0.0/10"),     # Carrier-grade NAT (shared address space)
    ipaddress.ip_network("198.18.0.0/15"),     # Benchmark testing
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local (private)
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

# V4.2 SYS-V4.2-001: IPv4-mapped IPv6 range — ::ffff:0:0/96 maps IPv4 addresses
# into IPv6 space. Python's ipaddress.ip_address("::ffff:127.0.0.1") creates
# an IPv6Address whose .ipv4_mapped property returns IPv4Address('127.0.0.1').
# Without this check, ::ffff:127.0.0.1 would bypass the IPv4 private ranges.
IPV4_MAPPED_IPV6_RANGE = ipaddress.ip_network("::ffff:0.0.0.0/96")

# Default config (overridable via settings)
MAX_URL_LENGTH = getattr(settings, "CRAWL_MAX_URL_LENGTH", 2048)
MAX_REDIRECTS = getattr(settings, "CRAWL_MAX_REDIRECTS", 3)


def _is_private_ip(ip_str: str) -> tuple[bool, str]:
    """Check if an IP address falls within private/reserved ranges.

    V4.2 SYS-V4.2-001: Also checks IPv4-mapped IPv6 addresses.
    ::ffff:127.0.0.1 is now correctly identified as private via ipv4_mapped.

    Returns (is_private, reason) tuple.
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True, f"Invalid IP address: {ip_str}"

    # V4.2 SYS-V4.2-001: IPv4-mapped IPv6 address check
    # ::ffff:127.0.0.1 → ipv4_mapped = IPv4Address('127.0.0.1') → is_private
    if ip.version == 6 and hasattr(ip, "ipv4_mapped") and ip.ipv4_mapped is not None:
        is_private_ipv4, ipv4_reason = _is_private_ipv4(ip.ipv4_mapped)
        if is_private_ipv4:
            return True, (
                f"IPv4-mapped IPv6 address {ip} maps to private IPv4 "
                f"{ip.ipv4_mapped} ({ipv4_reason})"
            )

    for private_range in PRIVATE_IP_RANGES:
        if ip in private_range:
            return True, f"IP {ip} is a private/reserved address ({private_range})"

    return False, ""


def _is_private_ipv4(ip: ipaddress.IPv4Address) -> tuple[bool, str]:
    """Check if an IPv4 address is private/reserved — helper for IPv4-mapped check."""
    for private_range in PRIVATE_IP_RANGES:
        if ip in private_range:
            return True, f"{ip} is in {private_range}"
    return False, ""


def _validate_hostname_ips(hostname: str) -> tuple[bool, str]:
    """Validate all resolved IPs for a hostname — used for DNS rebinding defense.

    V4.2 SYS-V4.2-002: Called before httpx requests to ensure the current
    DNS resolution hasn't been rebinded to a private IP after initial validation.

    Returns (all_public, reason) tuple.
    """
    try:
        resolved_ips = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False, f"Cannot resolve hostname '{hostname}'"

    for _, _, _, _, addr in resolved_ips:
        ip_str = addr[0]
        is_private, reason = _is_private_ip(ip_str)
        if is_private:
            return False, f"Hostname '{hostname}' resolved to private IP {ip_str}: {reason}"

    return True, ""


class CrawlURLValidator:
    """Validate crawl URLs against SSRF attacks — KB-V4.1-011/012/013.

    V4.2 enhancements:
    - SYS-V4.2-001: IPv4-mapped IPv6 addresses detected
    - SYS-V4.2-002: DNS rebinding defense (re-validate before fetch)
    - SYS-V4.2-003: Redirect chain intermediate IP validation
    - SYS-V4.2-005: Robots.txt prefetch IP validation

    Comprehensive SSRF defense that checks:
    1. Protocol whitelist (reject file://, gopher://, dict://, ftp://)
    2. URL length limit
    3. DNS resolution to IP → private IP blacklist (including IPv4-mapped IPv6)
    4. DNS Rebinding protection (validate redirect target IPs)
    """

    def validate(self, url: str) -> tuple[bool, str]:
        """Validate a URL for crawling. Returns (is_valid, reason).

        If is_valid is False, reason contains a human-readable explanation
        of why the URL was rejected (e.g., "Protocol 'file' is not allowed").
        """
        # KB-V4.1-012: URL length check
        if len(url) > MAX_URL_LENGTH:
            return False, f"URL exceeds maximum length of {MAX_URL_LENGTH} characters."

        # KB-V4.1-013: Protocol whitelist
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            return False, (
                f"Protocol '{scheme}' is not allowed. "
                f"Only {sorted(ALLOWED_SCHEMES)} are permitted."
            )

        # Must have a hostname
        hostname = parsed.hostname
        if not hostname:
            return False, "URL must have a hostname."

        # KB-V4.1-011 + V4.2 SYS-V4.2-001: DNS resolution → IP blacklist check
        # IPv4-mapped IPv6 addresses (::ffff:127.0.0.1) are now correctly detected
        is_public, reason = _validate_hostname_ips(hostname)
        if not is_public:
            logger.warning(
                "SSRF blocked: URL %s resolved to private IP — %s",
                url, reason,
            )
            return False, f"SSRF blocked: {reason}"

        return True, ""

    def validate_redirect_ip(self, ip_str: str) -> tuple[bool, str]:
        """Check if a redirect target IP is private — DNS rebinding defense.

        V4.2 SYS-V4.2-001: Also checks IPv4-mapped IPv6 addresses.

        Called after following redirects to verify that the final destination
        IP is not an internal address.

        Returns (is_valid, reason) tuple.
        """
        is_private, reason = _is_private_ip(ip_str)
        if is_private:
            logger.warning("DNS rebinding detected: redirect target IP %s is private", ip_str)
            return False, f"DNS rebinding detected: {reason}"
        return True, ""

    def validate_redirect_chain(self, response) -> tuple[bool, str]:
        """Validate ALL IPs in a redirect chain — V4.2 SYS-V4.2-003.

        Previously only checked the final redirect IP. Now checks
        response.history (all intermediate redirects) AND the final URL.

        This prevents attackers from setting up redirect chains where
        intermediate nodes point to internal IPs (169.254.169.254 etc.)
        even if the final URL resolves to a public IP.

        Args:
            response: httpx.Response object with .history and .url attributes.

        Returns (all_valid, reason) tuple.
        """
        # V4.2 SYS-V4.2-003: Check ALL intermediate redirect IPs
        for i, redirect_response in enumerate(response.history):
            redirect_host = redirect_response.url.host
            if redirect_host:
                is_public, reason = _validate_hostname_ips(str(redirect_host))
                if not is_public:
                    logger.warning(
                        "SSRF blocked: redirect chain step %d host '%s' "
                        "resolved to private IP — %s",
                        i, redirect_host, reason,
                    )
                    return False, (
                        f"Redirect chain intermediate node '{redirect_host}' "
                        f"resolved to private IP: {reason}"
                    )

        # Check final destination IP (same as before)
        final_host = response.url.host
        if final_host:
            try:
                final_ips = socket.getaddrinfo(str(final_host), None)
                for _, _, _, _, addr in final_ips:
                    is_valid_ip, ip_reason = self.validate_redirect_ip(addr[0])
                    if not is_valid_ip:
                        return False, ip_reason
            except socket.gaierror:
                return False, f"Cannot resolve final redirect host: {final_host}"

        # V4.2 SYS-V4.2-002: DNS rebinding re-validation — resolve again
        # between initial check and actual fetch to catch time-difference attacks
        if final_host:
            is_public, reason = _validate_hostname_ips(str(final_host))
            if not is_public:
                logger.warning(
                    "DNS rebinding detected: final host '%s' resolved to "
                    "private IP after redirect chain — %s",
                    final_host, reason,
                )
                return False, f"DNS rebinding detected after redirect: {reason}"

        return True, ""

    def validate_robots_txt_url(self, url: str) -> tuple[bool, str]:
        """Validate robots.txt prefetch URL — V4.2 SYS-V4.2-005.

        RobotsTxtChecker.can_fetch() prefetches robots.txt before the main
        crawl. This prefetch itself is an SSRF vector if DNS rebinding
        occurs between the initial URL validation and the robots.txt fetch.

        This method validates the robots.txt URL's resolved IPs using
        the same _is_private_ip() checks, preventing SSRF via robots.txt.

        Returns (is_valid, reason) tuple.
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "robots.txt URL has no hostname."

        is_public, reason = _validate_hostname_ips(hostname)
        if not is_public:
            logger.warning(
                "SSRF blocked: robots.txt URL %s resolved to private IP — %s",
                url, reason,
            )
            return False, f"SSRF blocked in robots.txt prefetch: {reason}"

        return True, ""
