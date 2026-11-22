import argparse
import csv
import json
import random
import re
import time
from pathlib import Path
from urllib.parse import urlencode


CDX_URL = "https://web.archive.org/cdx/search/cdx"
TOR_PROXY = "socks5h://127.0.0.1:9050"
PROXIES = {"http": TOR_PROXY, "https": TOR_PROXY}
TOR_CHECK_URL = "https://check.torproject.org/"
MAX_ATTEMPTS = 3


def movie_ids(csv_path):
    with csv_path.open(newline="", encoding="utf-8-sig") as source:
        reader = csv.DictReader(source)
        if "imdb_id" not in (reader.fieldnames or []):
            raise ValueError(f"{csv_path} must contain an 'imdb_id' column")

        seen = set()
        for row in reader:
            imdb_id = (row.get("imdb_id") or "").strip()
            if not re.fullmatch(r"tt\d+", imdb_id):
                raise ValueError(f"Invalid IMDb ID in CSV: {imdb_id!r}")
            if imdb_id not in seen:
                seen.add(imdb_id)
                yield imdb_id


def fetch_captures(imdb_id, responses_dir):
    try:
        import requests
    except ImportError as error:
        raise RuntimeError(
            'Install the scraper dependencies with: '
            'python -m pip install "requests[socks]" selenium'
        ) from error

    params = urlencode({
        "url": f"https://www.imdb.com/title/{imdb_id}",
        "output": "json",
        "fl": "timestamp,original,statuscode,mimetype,digest",
        "filter": ["statuscode:200", "mimetype:text/html"],
    }, doseq=True)
    response = requests.get(
        f"{CDX_URL}?{params}",
        proxies=PROXIES,
        timeout=60,
    )
    response.raise_for_status()

    cdx_data = response.content
    response_file = responses_dir / f"response_{imdb_id}.txt"
    response_file.write_bytes(cdx_data)

    captures = json.loads(cdx_data)
    if len(captures) < 2:
        raise RuntimeError(f"No archived HTML captures found for {imdb_id}")
    return captures[1:]


def latest_saved_date(dates_file):
    if not dates_file.exists():
        return None
    with dates_file.open(newline="", encoding="utf-8") as source:
        dates = [row["exact_date"] for row in csv.DictReader(source)]
    return dates[-1] if dates else None


def scrape_latest_capture(imdb_id, captures, descriptions_dir, responses_dir):
    try:
        from selenium import webdriver
        from selenium.common.exceptions import WebDriverException
        from selenium.webdriver.chrome.options import Options
    except ImportError as error:
        raise RuntimeError(
            'Install the scraper dependencies with: '
            'python -m pip install "requests[socks]" selenium'
        ) from error

    description_file = descriptions_dir / f"{imdb_id}.html"
    dates_file = responses_dir / f"exact_dates_{imdb_id}.csv"
    candidates = sorted(captures, key=lambda row: row[0], reverse=True)

    saved_date = latest_saved_date(dates_file)
    if (
        description_file.exists()
        and saved_date
        and candidates
        and candidates[0][0] == saved_date
    ):
        print(f"SKIP {imdb_id}: latest capture {saved_date} is already downloaded")
        return

    options = Options()
    options.add_argument("--headless=new")
    options.add_argument(f"--proxy-server=socks5://127.0.0.1:9050")
    driver = webdriver.Chrome(options=options)

    try:
        driver.set_page_load_timeout(90)
        driver.get(TOR_CHECK_URL)
        if (
            "Congratulations. This browser is configured to use Tor."
            not in driver.page_source
        ):
            raise RuntimeError(
                "Tor verification failed; confirm that the Tor proxy is running "
                "on 127.0.0.1:9050"
            )
        print("__TOR is OK")

        for capture in candidates:
            timestamp, original = capture[0], capture[1]
            archive_url = f"https://web.archive.org/web/{timestamp}id_/{original}"

            for attempt in range(1, MAX_ATTEMPTS + 1):
                try:
                    driver.get(archive_url)
                    time.sleep(3)
                    html = driver.page_source
                    lowered_html = html.lower()

                    if any(
                        marker in lowered_html
                        for marker in (
                            "403 forbidden",
                            "error 403",
                            "err_too_many_redirects",
                            "redirected you too many times",
                            "429 too many requests",
                        )
                    ):
                        print(f"NOT SCRAPPABLE: {timestamp}")
                        break
                    if len(html) < 1000:
                        raise ValueError("Page too short")

                    description_file.write_text(html, encoding="utf-8")
                    with dates_file.open("w", newline="", encoding="utf-8") as output:
                        writer = csv.DictWriter(output, fieldnames=["exact_date"])
                        writer.writeheader()
                        writer.writerow({"exact_date": timestamp})
                    print(f"OK {timestamp}: {description_file}")
                    return
                except (WebDriverException, ValueError) as error:
                    print(
                        f"Attempt {attempt}/{MAX_ATTEMPTS} failed "
                        f"for {imdb_id} at {timestamp}: {error}"
                    )
                    if attempt < MAX_ATTEMPTS:
                        time.sleep(10)

            time.sleep(random.uniform(1, 4))

        raise RuntimeError(
            f"No archived page could be downloaded for {imdb_id} "
            f"after trying {len(candidates)} captures"
        )
    finally:
        driver.quit()


def scrape_movie(imdb_id, responses_dir, descriptions_dir):
    captures = fetch_captures(imdb_id, responses_dir)
    scrape_latest_capture(imdb_id, captures, descriptions_dir, responses_dir)


def scrape_movies(
    csv_path,
    limit=1,
    responses_dir=Path("responses"),
    descriptions_dir=Path("descriptions"),
):
    if limit < 0:
        raise ValueError("limit must be zero or a positive integer")

    responses_dir.mkdir(parents=True, exist_ok=True)
    descriptions_dir.mkdir(parents=True, exist_ok=True)

    ids = movie_ids(csv_path)
    selected_ids = ids if limit == 0 else (
        imdb_id for index, imdb_id in enumerate(ids) if index < limit
    )
    for imdb_id in selected_ids:
        scrape_movie(imdb_id, responses_dir, descriptions_dir)


def main():
    parser = argparse.ArgumentParser(
        description="Save the latest archived IMDb title page using Selenium via Tor."
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path("imdb_ids_with_titles.csv"),
        help="CSV file with an imdb_id column (default: imdb_ids_with_titles.csv)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="number of IDs to scrape (default: 1; use 0 for all IDs)",
    )
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be zero or a positive integer")

    scrape_movies(args.csv, args.limit)


if __name__ == "__main__":
    main()
