"""
EY Data Collector — Standalone knowledge content crawler.

INTERNAL USE ONLY. 本脚本仅供 EY 内部员工用于构建新入职培训 AI 知识库，
仅从经授权许可的内部数据源或公开允许抓取的 EY 官方页面获取数据。
使用者须严格遵守 EY 信息安全政策、数据保护法规及目标网站的服务条款。
任何未经授权的抓取行为由使用者自行承担责任。
如涉及第三方版权内容，请确保已获得相应授权或仅提取摘要信息。

URL 校验模块 — SSRF 防护的独立实现，逻辑完全对齐
backend/apps/crawler/validators.py，但不依赖 Django。

防护层级（对齐现有代码的 V4.2 SYS-V4.2-001~005）：
- KB-V4.1-012: URL 长度限制
- KB-V4.1-013: 协议白名单（仅 http/https）
- KB-V4.1-011: 内部 IP 黑名单（私有/保留 IP 范围）
- V4.2 SYS-V4.2-001: IPv4-mapped IPv6 地址绕过检测
- V4.2 SYS-V4.2-002: DNS rebinding 时序攻击防护
- V4.2 SYS-V4.2-003: 重定向链中间节点 IP 校验
- V4.2 SYS-V4.2-005: robots.txt 预取 URL IP 校验

对于 source_type == "internal" 的数据源，SSRF IP 校验被跳过，
因为内网 URL 自然解析到私有 IP（如 SharePoint/Wiki）。
但 robots.txt 预取校验同样跳过（内网站点通常无 robots.txt）。
"""

import ipaddress
import socket
import logging
from urllib.parse import urlparse

from .config import CrawlerConfig

logger = logging.getLogger("ey_data_collector.validators")

# ────────────────────────────────────────────────────────────────────
# 协议白名单 — KB-V4.1-013: 仅允许 http 和 https
# ────────────────────────────────────────────────────────────────────

ALLOWED_SCHEMES = {"http", "https"}

# ────────────────────────────────────────────────────────────────────
# 私有/保留 IP 范围 — KB-V4.1-011: 拒绝内网访问
# 与 backend/apps/crawler/validators.py PRIVATE_IP_RANGES 完全一致
# ────────────────────────────────────────────────────────────────────

PRIVATE_IP_RANGES = [
    ipaddress.ip_network("127.0.0.0/8"),      # 回环地址
    ipaddress.ip_network("10.0.0.0/8"),        # A 类私有
    ipaddress.ip_network("172.16.0.0/12"),     # B 类私有
    ipaddress.ip_network("192.168.0.0/16"),    # C 类私有
    ipaddress.ip_network("169.254.0.0/16"),    # 链路本地（云元数据端点）
    ipaddress.ip_network("0.0.0.0/8"),         # "此网络"
    ipaddress.ip_network("100.64.0.0/10"),     #运营商级 NAT（共享地址空间）
    ipaddress.ip_network("198.18.0.0/15"),     # 基准测试
    ipaddress.ip_network("::1/128"),           # IPv6 回环
    ipaddress.ip_network("fc00::/7"),          # IPv6 唯一本地（私有）
    ipaddress.ip_network("fe80::/10"),         # IPv6 链路本地
]

# V4.2 SYS-V4.2-001: IPv4-mapped IPv6 范围 — ::ffff:0:0/96 将 IPv4 映射到 IPv6
IPV4_MAPPED_IPV6_RANGE = ipaddress.ip_network("::ffff:0.0.0.0/96")


# ────────────────────────────────────────────────────────────────────
# IP 私有地址检测
# ────────────────────────────────────────────────────────────────────

def _is_private_ip(ip_str: str) -> tuple[bool, str]:
    """检查 IP 地址是否属于私有/保留范围 — 对齐 validators.py _is_private_ip()。

    V4.2 SYS-V4.2-001: 同时检查 IPv4-mapped IPv6 地址。
    ::ffff:127.0.0.1 现在通过 ipv4_mapped 属性正确识别为私有地址。

    Returns:
        (is_private, reason) — is_private=True 表示属于私有/保留范围。
    """
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return True, f"无效 IP 地址: {ip_str}"

    # V4.2 SYS-V4.2-001: IPv4-mapped IPv6 地址检查
    # ::ffff:127.0.0.1 → ipv4_mapped = IPv4Address('127.0.0.1') → is_private
    if ip.version == 6 and hasattr(ip, "ipv4_mapped") and ip.ipv4_mapped is not None:
        is_private_ipv4, ipv4_reason = _is_private_ipv4(ip.ipv4_mapped)
        if is_private_ipv4:
            return True, (
                f"IPv4-mapped IPv6 地址 {ip} 映射到私有 IPv4 "
                f"{ip.ipv4_mapped} ({ipv4_reason})"
            )

    for private_range in PRIVATE_IP_RANGES:
        if ip in private_range:
            return True, f"IP {ip} 是私有/保留地址 ({private_range})"

    return False, ""


def _is_private_ipv4(ip: ipaddress.IPv4Address) -> tuple[bool, str]:
    """检查 IPv4 地址是否私有/保留 — IPv4-mapped 检查的辅助函数。"""
    for private_range in PRIVATE_IP_RANGES:
        if ip in private_range:
            return True, f"{ip} 属于 {private_range}"
    return False, ""


def _validate_hostname_ips(hostname: str) -> tuple[bool, str]:
    """校验主机名所有解析 IP — DNS rebinding 防护使用。

    V4.2 SYS-V4.2-002: 在 httpx 请求前调用，确保当前 DNS 解析
    未被重绑定到私有 IP（time-of-use 检查）。

    Returns:
        (all_public, reason) — all_public=True 表示所有解析 IP 都是公网地址。
    """
    try:
        resolved_ips = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False, f"无法解析主机名 '{hostname}'"

    for _, _, _, _, addr in resolved_ips:
        ip_str = addr[0]
        is_private, reason = _is_private_ip(ip_str)
        if is_private:
            return False, f"主机名 '{hostname}' 解析到私有 IP {ip_str}: {reason}"

    return True, ""


# ────────────────────────────────────────────────────────────────────
# SSRF URL 校验器
# ────────────────────────────────────────────────────────────────────

class CrawlURLValidator:
    """SSRF URL 校验器 — 独立实现，逻辑对齐 backend/apps/crawler/validators.py。

    从 CrawlerConfig 读取配置参数（替代 django.conf.settings），
    保持与 Django 版 CrawlURLValidator 完全一致的防护逻辑。

    内部数据源（source_type == "internal"）跳过 IP 校验，
    因为内网 URL 自然解析到私有 IP。
    """

    def __init__(self, config: CrawlerConfig):
        self.config = config
        self.max_url_length = config.max_url_length
        self.max_redirects = config.max_redirects

    def validate(self, url: str, is_internal: bool = False) -> tuple[bool, str]:
        """校验爬取 URL — 对齐 validators.py CrawlURLValidator.validate()。

        对于内部数据源（is_internal=True），跳过 IP 黑名单校验，
        因为内网 SharePoint/Wiki URL 自然解析到私有 IP（10.x / 172.16.x 等）。
        其他防护（协议白名单、URL 长度）仍然执行。

        Args:
            url: 待校验的 URL。
            is_internal: 是否为内部数据源（跳过 IP 校验）。

        Returns:
            (is_valid, reason) — is_valid=False 时 reason 含拒绝理由。
        """
        # KB-V4.1-012: URL 长度校验
        if len(url) > self.max_url_length:
            return False, f"URL 超过最大长度限制 {self.max_url_length} 字符。"

        # KB-V4.1-013: 协议白名单
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        if scheme not in ALLOWED_SCHEMES:
            return False, (
                f"协议 '{scheme}' 不允许。仅允许 {sorted(ALLOWED_SCHEMES)}。"
            )

        # 必须包含主机名
        hostname = parsed.hostname
        if not hostname:
            return False, "URL 必须包含主机名。"

        # KB-V4.1-011 + V4.2 SYS-V4.2-001: DNS 解析 → IP 黑名单检查
        # 内部数据源跳过此步骤（内网 URL 解析到私有 IP 是正常现象）
        if is_internal:
            logger.info("内部数据源 — 跳过 SSRF IP 校验: %s", url)
        else:
            is_public, reason = _validate_hostname_ips(hostname)
            if not is_public:
                logger.warning("SSRF 阻断: URL %s 解析到私有 IP — %s", url, reason)
                return False, f"SSRF 阻断: {reason}"

        return True, ""

    def validate_redirect_ip(self, ip_str: str) -> tuple[bool, str]:
        """检查重定向目标 IP 是否为私有地址 — DNS rebinding 防护。"""
        is_private, reason = _is_private_ip(ip_str)
        if is_private:
            logger.warning("DNS rebinding 检测: 重定向目标 IP %s 为私有地址", ip_str)
            return False, f"DNS rebinding 检测: {reason}"
        return True, ""

    def validate_redirect_chain(
        self,
        response,
        is_internal: bool = False,
    ) -> tuple[bool, str]:
        """校验重定向链中所有 IP — V4.2 SYS-V4.2-003。

        对于内部数据源，跳过中间节点 IP 校验（内网重定向自然指向私有 IP）。

        Args:
            response: httpx.Response 对象（含 .history 和 .url）。
            is_internal: 是否为内部数据源。

        Returns:
            (all_valid, reason) — all_valid=False 时含拒绝理由。
        """
        if is_internal:
            # 内部数据源跳过重定向链 IP 校验
            logger.debug("内部数据源 — 跳过重定向链 IP 校验")
            return True, ""

        # V4.2 SYS-V4.2-003: 检查所有中间重定向 IP
        for i, redirect_response in enumerate(response.history):
            redirect_host = redirect_response.url.host
            if redirect_host:
                is_public, reason = _validate_hostname_ips(str(redirect_host))
                if not is_public:
                    logger.warning(
                        "SSRF 阻断: 重定向链第 %d 步主机 '%s' "
                        "解析到私有 IP — %s",
                        i, redirect_host, reason,
                    )
                    return False, (
                        f"重定向链中间节点 '{redirect_host}' "
                        f"解析到私有 IP: {reason}"
                    )

        # 检查最终目标 IP
        final_host = response.url.host
        if final_host:
            try:
                final_ips = socket.getaddrinfo(str(final_host), None)
                for _, _, _, _, addr in final_ips:
                    is_valid_ip, ip_reason = self.validate_redirect_ip(addr[0])
                    if not is_valid_ip:
                        return False, ip_reason
            except socket.gaierror:
                return False, f"无法解析最终重定向主机: {final_host}"

        # V4.2 SYS-V4.2-002: DNS rebinding 重新校验 — resolve again
        if final_host:
            is_public, reason = _validate_hostname_ips(str(final_host))
            if not is_public:
                logger.warning(
                    "DNS rebinding 检测: 最终主机 '%s' 在重定向链后 "
                    "解析到私有 IP — %s",
                    final_host, reason,
                )
                return False, f"重定向后发现 DNS rebinding: {reason}"

        return True, ""

    def validate_robots_txt_url(self, url: str) -> tuple[bool, str]:
        """校验 robots.txt 预取 URL — V4.2 SYS-V4.2-005。

        与 backend/apps/crawler/validators.py validate_robots_txt_url() 一致。
        阻止 robots.txt 预取本身的 SSRF 攻击向量。

        Returns:
            (is_valid, reason) — is_valid=False 时含拒绝理由。
        """
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return False, "robots.txt URL 缺少主机名。"

        is_public, reason = _validate_hostname_ips(hostname)
        if not is_public:
            logger.warning(
                "SSRF 阻断: robots.txt URL %s 解析到私有 IP — %s",
                url, reason,
            )
            return False, f"robots.txt 预取 SSRF 阻断: {reason}"

        return True, ""
