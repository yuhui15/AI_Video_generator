"""Collect public looksmaxxing-related articles and image metadata."""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.robotparser
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

import feedparser
import requests
import trafilatura
from bs4 import BeautifulSoup


USER_AGENT = "LooksmaxxingPublicCollector/1.0 (+public-content-only)"
RSS_TEMPLATES = (
    "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q={query}&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
    "https://www.bing.com/news/search?q={query}&format=rss",
)
QUERIES = (
    "looksmaxxing",
    "looksmaxing",
    "PSL facial aesthetics",
    "clavicular looksmaxxing",
    "top model facial aesthetics",
    "skinmaxxing hairmaxxing gymmaxxing",
)
CATEGORY_TERMS = {
    "psl": ("psl", "facial aesthetics", "face rating"),
    "people": ("clavicular", "top model", "model", "influencer"),
    "community": ("looksmaxxing", "looksmaxing", "looksmax"),
    "grooming": ("skinmaxxing", "skincare", "hairmaxxing", "hairstyle"),
}


@dataclass
class CollectedArticle:
    title: str
    url: str
    source: str
    summary: str
    text: str
    categories: list[str]
    image_urls: list[str]
    image_rights: str
    collected_at: str


def categories_for(text: str) -> list[str]:
    haystack = text.lower()
    return [
        category
        for category, terms in CATEGORY_TERMS.items()
        if any(term in haystack for term in terms)
    ] or ["other"]


def allowed_by_robots(url: str, cache: dict[str, urllib.robotparser.RobotFileParser]) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in cache:
        parser = urllib.robotparser.RobotFileParser()
        parser.set_url(urljoin(origin, "/robots.txt"))
        try:
            parser.read()
        except OSError:
            return False
        cache[origin] = parser
    return cache[origin].can_fetch(USER_AGENT, url)


def clean(value: str, limit: int = 800) -> str:
    return re.sub(r"\s+", " ", value).strip()[:limit]


def image_urls(page_url: str, soup: BeautifulSoup) -> list[str]:
    candidates: list[str] = []
    for selector in (
        ('meta', {'property': 'og:image'}),
        ('meta', {'name': 'twitter:image'}),
        ('meta', {'property': 'twitter:image'}),
    ):
        for tag in soup.find_all(*selector):
            value = tag.get("content")
            if value:
                candidates.append(urljoin(page_url, value))
    for tag in soup.find_all("img", src=True):
        candidates.append(urljoin(page_url, str(tag["src"])))
    return list(dict.fromkeys(
        value for value in candidates
        if value.startswith(("http://", "https://"))
    ))[:10]


def fetch_feed(url: str) -> list[dict[str, str]]:
    response = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/rss+xml, application/xml"},
        timeout=20,
    )
    response.raise_for_status()
    feed = feedparser.parse(response.content)
    return [
        {
            "title": clean(BeautifulSoup(str(entry.get("title", "")), "html.parser").get_text(" ")),
            "url": str(entry.get("link", "")).strip(),
            "summary": clean(BeautifulSoup(
                str(entry.get("summary", entry.get("description", ""))),
                "html.parser",
            ).get_text(" ")),
            "source": clean(str(entry.get("source", {}).get("title", ""))) or "公开 RSS",
        }
        for entry in feed.entries
        if str(entry.get("link", "")).strip() and str(entry.get("title", "")).strip()
    ]


def collect(
    max_articles: int,
    delay: float,
    rss_url: str | None,
    queries: tuple[str, ...] = QUERIES,
) -> list[CollectedArticle]:
    urls = [rss_url] if rss_url else [
        template.format(query=quote_plus(query))
        for query in queries
        for template in RSS_TEMPLATES
    ]
    candidates: list[dict[str, str]] = []
    seen: set[str] = set()
    for url in urls:
        try:
            for entry in fetch_feed(url):
                if entry["url"] not in seen:
                    seen.add(entry["url"])
                    candidates.append(entry)
                    if len(candidates) >= max_articles:
                        break
        except requests.RequestException as exc:
            print(f"Warning: RSS unavailable: {url} ({exc})", file=sys.stderr)
        if len(candidates) >= max_articles:
            break

    robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
    results: list[CollectedArticle] = []
    for entry in candidates:
        text = entry["summary"]
        images: list[str] = []
        if allowed_by_robots(entry["url"], robots_cache):
            try:
                response = requests.get(entry["url"], headers={"User-Agent": USER_AGENT}, timeout=20)
                response.raise_for_status()
                soup = BeautifulSoup(response.text, "html.parser")
                images = image_urls(entry["url"], soup)
                extracted = trafilatura.extract(response.text, include_comments=False, include_tables=False)
                if extracted:
                    text = clean(extracted, 5000)
            except requests.RequestException as exc:
                print(f"Warning: page unavailable: {entry['url']} ({exc})", file=sys.stderr)
        else:
            print(f"Page skipped by robots.txt; retaining RSS metadata: {entry['url']}", file=sys.stderr)
        results.append(CollectedArticle(
            title=entry["title"],
            url=entry["url"],
            source=entry["source"],
            summary=entry["summary"],
            text=text,
            categories=categories_for(f"{entry['title']} {text}"),
            image_urls=images,
            image_rights="unknown_verify_license_before_use",
            collected_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        ))
        time.sleep(delay)
    return results


def collect_forum_text(max_articles: int, delay: float = 0.8) -> list[CollectedArticle]:
    """Collect text from public forum HTML pages without collecting images."""
    base_url = "https://forum.looksmaxxing.com/"
    robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
    queue = [base_url]
    seen_pages: set[str] = set()
    results: list[CollectedArticle] = []
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})
    sitemap_url = urljoin(base_url, "sitemap.xml")
    if allowed_by_robots(sitemap_url, robots_cache):
        try:
            sitemap_response = session.get(sitemap_url, timeout=20)
            sitemap_response.raise_for_status()
            sitemap_soup = BeautifulSoup(sitemap_response.text, "html.parser")
            sitemap_pages = [
                loc.get_text(strip=True)
                for loc in sitemap_soup.find_all("loc")
                if loc.get_text(strip=True).startswith(base_url)
            ]
            for child_sitemap in sitemap_pages[:2]:
                if not allowed_by_robots(child_sitemap, robots_cache):
                    continue
                child_response = session.get(child_sitemap, timeout=20)
                child_response.raise_for_status()
                child_soup = BeautifulSoup(child_response.text, "html.parser")
                queue.extend(
                    loc.get_text(strip=True)
                    for loc in child_soup.find_all("loc")
                    if loc.get_text(strip=True).startswith(base_url)
                )
        except requests.RequestException as exc:
            print(f"Warning: forum sitemap unavailable: {exc}", file=sys.stderr)
    while queue and len(seen_pages) < 30 and len(results) < max_articles:
        page_url = queue.pop(0).split("#", 1)[0]
        parsed = urlparse(page_url)
        if (
            page_url in seen_pages
            or parsed.netloc != urlparse(base_url).netloc
            or "/attachments/" in parsed.path
            or not allowed_by_robots(page_url, robots_cache)
        ):
            continue
        seen_pages.add(page_url)
        try:
            response = session.get(page_url, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            print(f"Warning: forum page unavailable: {page_url} ({exc})", file=sys.stderr)
            continue
        soup = BeautifulSoup(response.text, "html.parser")
        for link in soup.select("a[href]"):
            href = urljoin(page_url, str(link["href"])).split("#", 1)[0]
            href_path = urlparse(href).path
            if (
                urlparse(href).netloc == parsed.netloc
                and href not in seen_pages
                and "/attachments/" not in href_path
                and "/login/" not in href_path
            ):
                queue.append(href)
        extracted = trafilatura.extract(
            response.text, include_comments=False, include_tables=False
        )
        text = clean(extracted or soup.get_text(" ", strip=True), 5000)
        title = clean(soup.title.get_text(" ", strip=True) if soup.title else page_url, 300)
        if len(text) >= 80:
            results.append(CollectedArticle(
                title=title,
                url=page_url,
                source="forum.looksmaxxing.com",
                summary=clean(text, 600),
                text=text,
                categories=categories_for(f"{title} {text}"),
                image_urls=[],
                image_rights="not_collected",
                collected_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            ))
        time.sleep(delay)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-articles", type=int, default=30)
    parser.add_argument("--delay", type=float, default=1.0, help="每个页面之间的请求间隔（秒）")
    parser.add_argument("--rss-url", help="可选：只使用一个公开 RSS 地址")
    parser.add_argument("--output-dir", default="output/collection")
    args = parser.parse_args()
    if not 1 <= args.max_articles <= 200:
        parser.error("--max-articles must be between 1 and 200")
    if args.delay < 0.2:
        parser.error("--delay must be at least 0.2 seconds")

    records = collect(args.max_articles, args.delay, args.rss_url)
    destination = Path(args.output_dir)
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / "articles.jsonl").open("w", encoding="utf-8") as handle:
        for record in records:
            handle.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    images = [
        {"article_title": record.title, "article_url": record.url, "source": record.source,
         "image_url": image, "rights": record.image_rights}
        for record in records for image in record.image_urls
    ]
    (destination / "images.json").write_text(
        json.dumps(images, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"采集完成：{len(records)} 篇公开文章")
    print(f"文章数据：{(destination / 'articles.jsonl').resolve()}")
    print(f"图片链接：{(destination / 'images.json').resolve()}（仅链接，未下载原图）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
