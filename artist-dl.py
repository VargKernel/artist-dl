#!/usr/bin/env python3
import argparse
import sys
import os
import re
import hashlib
import logging
from urllib.parse import urlparse, parse_qs, unquote_plus, quote_plus

import requests

# tqdm is optional: if it is not installed, the script still works
try:
    from tqdm import tqdm
except ImportError:
    class tqdm:
        def __init__(self, total=None, desc=None, unit=None):
            self.total = total
            self.desc = desc
            self.unit = unit
            self.n = 0

        def update(self, n=1):
            self.n += n

        def close(self):
            pass

        @staticmethod
        def write(message):
            print(message)


VERSION = "1.2.0"

HELP = """
Description: A CLI utility for processing author post URLs from popular booru sites.

Usage:
  {name} [OPTIONS] URL [URL...]

Examples:
  python3 {name} https://reactor.cc/tag/artist
  python3 {name} URL1 URL2 URL3...
  python3 {name} -i input_urls.txt -o output_links.txt -f failed_links.txt -l run.log

Options:
  -h, --help
  -v, --version
  -i, --input-file FILE
  -o, --output-file FILE
  -f, --failed-file FILE
  -l, --log-file FILE
"""

URLS = {
    "reactor.cc": "https://reactor.cc/tag/{author}",
    "yande.re": "https://yande.re/post?tags={author}",
    "konachan.com": "https://konachan.com/post?tags={author}",
    "e621.net": "https://e621.net/posts?tags={author}",
    "rule34.xxx": "https://rule34.xxx/index.php?page=post&s=list&tags={author}",
}

HEADERS = {
    "User-Agent": "Mozilla/5.0"
}

URL_REGEX = re.compile(r'https?://[^\s<>"\']+')

CACHE_DIR = ".cache"
NOT_FOUND_TEXT = "Nobody here but us chickens!"

# Sites that often return 403 due to access/age gates, but should be treated as "empty".
SPECIAL_EMPTY_403_SITES = {"e621.net", "rule34.xxx"}

LOGGER = logging.getLogger("author_post_link_processor")
SESSION = requests.Session()
SESSION.headers.update(HEADERS)


class TqdmLoggingHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            tqdm.write(msg)
        except Exception:
            self.handleError(record)


def setup_logging(log_file: str | None) -> None:
    LOGGER.handlers.clear()
    LOGGER.setLevel(logging.DEBUG)

    console_handler = TqdmLoggingHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    LOGGER.addHandler(console_handler)

    if log_file:
        file_handler = logging.FileHandler(os.path.abspath(log_file), encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter("%(asctime)s | %(levelname)s | %(message)s"))
        LOGGER.addHandler(file_handler)


def detect_supported_site(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()

    if host.endswith("reactor.cc"):
        return "reactor.cc"
    if host.endswith("yande.re"):
        return "yande.re"
    if host.endswith("e621.net"):
        return "e621.net"
    if host.endswith("rule34.xxx"):
        return "rule34.xxx"
    if host.endswith("konachan.com"):
        return "konachan.com"

    return None


def extract_author_from_url(url: str) -> str | None:
    parsed = urlparse(url.strip())
    if not parsed.scheme or not parsed.netloc:
        return None

    host = parsed.netloc.lower()
    path_parts = [part for part in parsed.path.split("/") if part]
    query_tags = parse_qs(parsed.query).get("tags")

    if query_tags:
        return unquote_plus(query_tags[0]).strip() or None

    if host.endswith("reactor.cc"):
        if len(path_parts) >= 2 and path_parts[0] == "tag":
            return unquote_plus(path_parts[1]).strip() or None
        return unquote_plus(path_parts[-1]).strip() if path_parts else None

    if host.endswith(("yande.re", "konachan.com", "e621.net", "rule34.xxx")):
        return unquote_plus(path_parts[-1]).strip() if path_parts else None

    return None


def cache_path_for(url: str) -> str:
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache_name = hashlib.sha256(url.encode("utf-8")).hexdigest() + ".html"
    return os.path.join(CACHE_DIR, cache_name)


def download_page(url: str, site: str) -> tuple[str | None, str]:
    """
    Returns:
      (content, status)

    status:
      - "ok"    : page downloaded successfully and contains real content
      - "empty" : page is empty / blocked / no results
      - "fail"  : hard failure
    """
    filename = cache_path_for(url)

    if os.path.exists(filename):
        try:
            with open(filename, "r", encoding="utf-8") as f:
                content = f.read()

            LOGGER.info("Cache hit: %s", url)

            if content == NOT_FOUND_TEXT:
                LOGGER.info("Empty result: %s", url)
                return content, "empty"

            return content, "ok"
        except Exception as e:
            LOGGER.debug("Cache read failed for %s: %s", url, e)

    try:
        response = SESSION.get(url, timeout=10)
    except Exception as e:
        LOGGER.warning("Exception downloading %s: %s", url, e)
        return None, "fail"

    if response.status_code == 200:
        content = response.text

        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            LOGGER.debug("Cache write failed for %s: %s", url, e)

        LOGGER.info("Downloaded: %s", url)

        if NOT_FOUND_TEXT in content:
            LOGGER.info("Empty result: %s", url)
            return content, "empty"

        return content, "ok"

    if response.status_code == 403 and site in SPECIAL_EMPTY_403_SITES:
        try:
            with open(filename, "w", encoding="utf-8") as f:
                f.write(NOT_FOUND_TEXT)
        except Exception as e:
            LOGGER.debug("Cache write failed for empty 403 page %s: %s", url, e)

        LOGGER.info("Downloaded: %s", url)
        LOGGER.info("Empty result: %s", url)
        return NOT_FOUND_TEXT, "empty"

    LOGGER.warning("Failed to download %s (status %s)", url, response.status_code)
    return None, "fail"


def collect_input_links(args) -> list[str]:
    # Priority: CLI URLs > file
    if args.urls:
        return list(dict.fromkeys(args.urls))

    if args.input_file:
        path = os.path.abspath(args.input_file)

        if not os.path.isfile(path):
            print(f"Error: file not found: {path}")
            sys.exit(1)

        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            print(f"Error: cannot read file {path}: {e}")
            sys.exit(1)

        links = URL_REGEX.findall(content)
        if not links:
            print(f"Error: no links found in {path}")
            sys.exit(1)

        return list(dict.fromkeys(links))

    print("Error: no input provided (URL or -i required)")
    sys.exit(1)


def format_grouped_sections(sections: dict[str, list[str]], order: list[str]) -> str:
    lines: list[str] = []

    for section_name in order:
        items = sections.get(section_name, [])
        if not items:
            continue

        lines.append(f"# {section_name}:")
        lines.extend(items)
        lines.append("")

    if not lines:
        return ""

    return "\n".join(lines).rstrip() + "\n"


def rewrite_grouped_file(path: str, sections: dict[str, list[str]], order: list[str]) -> None:
    if not path:
        return

    content = format_grouped_sections(sections, order)
    tmp_path = path + ".tmp"

    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(content)

    os.replace(tmp_path, path)


def print_grouped_sections(sections: dict[str, list[str]], order: list[str]) -> None:
    for section_name in order:
        items = sections.get(section_name, [])
        if not items:
            continue

        print(f"# {section_name}:")
        for item in items:
            print(item)
        print()


def main():
    parser = argparse.ArgumentParser(add_help=False)

    parser.add_argument("urls", nargs="*")
    parser.add_argument("-h", "--help", action="store_true")
    parser.add_argument("-v", "--version", action="store_true")
    parser.add_argument("-i", "--input-file")
    parser.add_argument("-o", "--output-file")
    parser.add_argument("-f", "--failed-file")
    parser.add_argument("-l", "--log-file")

    args = parser.parse_args()

    if len(sys.argv) == 1 or args.help:
        print(HELP.format(name=os.path.basename(sys.argv[0])))
        sys.exit(0)

    if args.version:
        print(VERSION)
        sys.exit(0)

    setup_logging(args.log_file)

    links = collect_input_links(args)
    LOGGER.info("Total input links: %d", len(links))

    total_attempts = len(links) * len(URLS)
    progress = tqdm(total=total_attempts, desc="Processing", unit="attempt")

    site_order = list(URLS.keys())
    failed_order = ["invalid_input"] + site_order

    found_links: dict[str, list[str]] = {site: [] for site in site_order}
    found_seen: dict[str, set[str]] = {site: set() for site in site_order}

    failed_entries: dict[str, list[str]] = {site: [] for site in failed_order}
    failed_seen: dict[str, set[str]] = {site: set() for site in failed_order}

    output_path = os.path.abspath(args.output_file) if args.output_file else None
    failed_path = os.path.abspath(args.failed_file) if args.failed_file else None

    try:
        for index, source_url in enumerate(links, start=1):
            LOGGER.info("Source %d/%d: %s", index, len(links), source_url)

            source_site = detect_supported_site(source_url)
            author = extract_author_from_url(source_url)

            LOGGER.info("Detected source site: %s", source_site if source_site else "unsupported")
            LOGGER.info("Extracted author: %s", author if author else "none")

            if not source_site or not author:
                entry = f"{source_url} | invalid"
                if entry not in failed_seen["invalid_input"]:
                    failed_seen["invalid_input"].add(entry)
                    failed_entries["invalid_input"].append(entry)
                    LOGGER.info("Recorded invalid input: %s", source_url)

                    if failed_path:
                        rewrite_grouped_file(failed_path, failed_entries, failed_order)

                progress.update(len(URLS))
                continue

            encoded_author = quote_plus(author)

            for target_site in site_order:
                template = URLS[target_site]
                link = template.format(author=encoded_author)

                LOGGER.info("Checking %s -> %s", target_site, link)

                page_content, status = download_page(link, target_site)

                if status == "fail":
                    entry = f"{link} | failed"
                    if entry not in failed_seen[target_site]:
                        failed_seen[target_site].add(entry)
                        failed_entries[target_site].append(entry)
                        LOGGER.info("Recorded failure for %s", target_site)

                        if failed_path:
                            rewrite_grouped_file(failed_path, failed_entries, failed_order)

                    progress.update(1)
                    continue

                if status == "empty" or not page_content or NOT_FOUND_TEXT in page_content:
                    LOGGER.info("No posts found for %s", link)
                    progress.update(1)
                    continue

                if link not in found_seen[target_site]:
                    found_seen[target_site].add(link)
                    found_links[target_site].append(link)
                    LOGGER.info("Recorded result for %s", target_site)

                    if output_path:
                        rewrite_grouped_file(output_path, found_links, site_order)

                else:
                    LOGGER.info("Duplicate skipped for %s", link)

                progress.update(1)

            # Update output after each source URL so files change in real time,
            # while still keeping the grouped-by-site format stable.
            if output_path:
                rewrite_grouped_file(output_path, found_links, site_order)
            if failed_path:
                rewrite_grouped_file(failed_path, failed_entries, failed_order)

    finally:
        progress.close()

        # Final flush to make sure files are complete.
        if output_path:
            rewrite_grouped_file(output_path, found_links, site_order)
        if failed_path:
            rewrite_grouped_file(failed_path, failed_entries, failed_order)

    if not args.output_file:
        print_grouped_sections(found_links, site_order)

    LOGGER.info("Done")


if __name__ == "__main__":
    main()