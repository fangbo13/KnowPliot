#!/usr/bin/env python3
"""Simple crawler using only built-in libraries."""

import urllib.request
import urllib.robotparser
import ssl
import time
import random
import json
import os
import re
import hashlib
from urllib.parse import urlparse
from datetime import datetime

# Create SSL context
ssl_context = ssl.create_default_context()

# Headers mimicking a browser
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
}

def clean_html(text):
    """Remove HTML tags and clean text."""
    # Remove script and style tags
    text = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', text, flags=re.DOTALL)
    # Remove HTML tags
    text = re.sub(r'<[^>]+>', ' ', text)
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Remove JS/CSS content
    text = re.sub(r'\{[^}]*\}', '', text)
    return text.strip()

def fetch_url(url, max_retries=3):
    """Fetch a URL with retry logic."""
    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            response = urllib.request.urlopen(req, timeout=15)
            content = response.read().decode('utf-8', errors='ignore')
            return content, response.status
        except Exception as e:
            print(f"Attempt {attempt + 1}/{max_retries} failed for {url}: {e}")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None, 0
    return None, 0

def extract_title(html):
    """Extract title from HTML."""
    match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
    if match:
        return clean_html(match.group(1))
    return ""

def crawl_pages(urls, output_dir):
    """Crawl a list of URLs and save content."""
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(f"{output_dir}/pages", exist_ok=True)

    results = []
    total_chars = 0

    for i, (name, url) in enumerate(urls, 1):
        print(f"[{i}/{len(urls)}] Crawling: {name} - {url}")

        html, status = fetch_url(url)
        if html is None:
            print(f"  Failed to fetch {url}")
            continue

        # Extract title and content
        title = extract_title(html)
        text = clean_html(html)

        # Skip if too short
        if len(text) < 500:
            print(f"  Content too short ({len(text)} chars), skipping")
            continue

        # Save to file
        safe_name = re.sub(r'[^\w\-_]', '_', name)[:50]
        filename = f"{output_dir}/pages/page_{i:03d}_{safe_name}.md"

        with open(filename, 'w', encoding='utf-8') as f:
            f.write(f"# {name}\n\n")
            f.write(f"**Source:** {url}\n\n")
            f.write(f"**Crawled:** {datetime.now().isoformat()}\n\n")
            f.write(f"**Title:** {title}\n\n")
            f.write("---\n\n")
            f.write(text)

        results.append({
            'name': name,
            'url': url,
            'title': title,
            'filename': filename,
            'chars': len(text),
        })

        total_chars += len(text)
        print(f"  Saved: {filename} ({len(text)} chars)")

        # Rate limiting
        delay = random.uniform(2, 5)
        print(f"  Waiting {delay:.1f}s...")
        time.sleep(delay)

    # Generate index
    generate_index(results, total_chars, output_dir)

    return results, total_chars

def generate_index(results, total_chars, output_dir):
    """Generate index.md with summary."""
    index_path = f"{output_dir}/index.md"

    with open(index_path, 'w', encoding='utf-8') as f:
        f.write("# EY Data Collector - Knowledge Base Index\n\n")
        f.write(f"**Generated:** {datetime.now().isoformat()}\n\n")
        f.write(f"**Total Sources:** {len(results)}\n\n")
        f.write(f"**Total Characters:** {total_chars:,}\n\n")
        f.write("## Crawled Sources\n\n")

        for i, r in enumerate(results, 1):
            f.write(f"{i}. [{r['name']}]({r['filename']}) - {r['chars']:,} chars\n")

        f.write("\n## Source Details\n\n")

        for r in results:
            f.write(f"### {r['name']}\n\n")
            f.write(f"- **URL:** {r['url']}\n")
            f.write(f"- **Title:** {r['title']}\n")
            f.write(f"- **File:** [{r['filename']}]({r['filename']})\n")
            f.write(f"- **Characters:** {r['chars']:,}\n\n")

    print(f"\nIndex generated: {index_path}")
    print(f"Total sources: {len(results)}")
    print(f"Total characters: {total_chars:,}")

# Sources to crawl
SOURCES = [
    ("EY Careers", "https://www.ey.com/en_careers"),
    ("EY About Us", "https://www.ey.com/en_gl/about-us"),
    ("EY Our Purpose", "https://www.ey.com/en_gl/about-us/our-purpose"),
    ("EY Our Values", "https://www.ey.com/en_gl/about-us/our-values"),
    ("EY Global Review", "https://www.ey.com/en_gl/global-review"),
    ("EY Culture", "https://www.ey.com/en_careers/culture"),
    ("EY Insights", "https://www.ey.com/en_gl/insights"),
    ("EY Industries", "https://www.ey.com/en_gl/industries"),
    ("EY Services", "https://www.ey.com/en_gl/services"),
    ("EY Diversity", "https://www.ey.com/en_gl/about-us/our-commitment-to-diversity-and-inclusiveness"),
    ("Wikipedia Ernst & Young", "https://en.wikipedia.org/wiki/Ernst_%26_Young"),
    ("Wikipedia Onboarding", "https://en.wikipedia.org/wiki/Onboarding"),
    ("Wikipedia Management Consulting", "https://en.wikipedia.org/wiki/Management_consulting"),
    ("Wikipedia Auditing", "https://en.wikipedia.org/wiki/Auditing"),
    ("Wikipedia Accounting", "https://en.wikipedia.org/wiki/Accounting"),
    ("Wikipedia Professional Services", "https://en.wikipedia.org/wiki/Professional_services"),
    ("Wikipedia Big Four", "https://en.wikipedia.org/wiki/Big_Four_accounting_firms"),
    ("Wikipedia Corporate Culture", "https://en.wikipedia.org/wiki/Organizational_culture"),
    ("Wikipedia Business Ethics", "https://en.wikipedia.org/wiki/Business_ethics"),
    ("Wikipedia Tax Advisor", "https://en.wikipedia.org/wiki/Tax_advisor"),
]

if __name__ == "__main__":
    output_dir = "d:/Github/Onborading-AI/crawled_knowledge"
    results, total_chars = crawl_pages(SOURCES, output_dir)
    print(f"\nDone! Crawled {len(results)} pages, {total_chars:,} characters total.")
