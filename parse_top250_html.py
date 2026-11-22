import csv
import json
import re
from pathlib import Path

from bs4 import BeautifulSoup


FIELDS = [
    "snapshot",
    "rank",
    "title",
    "year",
    "imdb_id",
    "title_url",
    "rating",
    "votes",
    "source_file",
]


def title_id(url):
    match = re.search(r"(tt\d+)", url or "")
    return match.group(1) if match else ""


def attribute_value(element):
    if element is None:
        return ""
    return (
        element.get("data-value")
        or element.get("content")
        or element.get_text(" ", strip=True)
    )


def clean_title(link):
    title = link.get_text(" ", strip=True)
    if title:
        return title
    image = link.find("img")
    if image:
        title = image.get("alt") or image.get("title") or ""
        return re.sub(r"\s+\(\d{4}\)\s*$", "", title).strip()
    return ""


def snapshot_name(source):
    return source.stem.split("_")[0]


def parse_json_ld(soup, source):
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.string or script.get_text())
        except json.JSONDecodeError:
            continue

        pending = [data]
        while pending:
            value = pending.pop()
            if isinstance(value, list):
                pending.extend(value)
                continue
            if not isinstance(value, dict):
                continue

            items = value.get("itemListElement")
            if isinstance(items, list):
                rows = []
                for position, entry in enumerate(items, start=1):
                    if not isinstance(entry, dict):
                        continue
                    movie = entry.get("item", entry)
                    if not isinstance(movie, dict):
                        continue
                    url = movie.get("url", "")
                    rating = movie.get("aggregateRating") or {}
                    rows.append({
                        "snapshot": snapshot_name(source),
                        "rank": entry.get("position", position),
                        "title": movie.get("name", ""),
                        "year": "",
                        "imdb_id": title_id(url),
                        "title_url": url,
                        "rating": rating.get("ratingValue", ""),
                        "votes": rating.get("ratingCount", ""),
                        "source_file": str(source),
                    })
                if rows:
                    return sorted(rows, key=lambda row: int(row["rank"]))[:250]

            pending.extend(value.values())
    return []


def parse_modern_rows(soup, source):
    rows = []
    snapshot = snapshot_name(source)

    for tr in soup.select("tr"):
        title_cell = tr.select_one("td.titleColumn")
        if title_cell is not None:
            title_link = title_cell.select_one("a[href]")
        else:
            title_link = next(
                (
                    link
                    for link in tr.select("a[href]")
                    if title_id(link.get("href", ""))
                ),
                None,
            )
        if title_link is None:
            continue

        title_url = title_link.get("href", "")

        rank_element = tr.select_one('[name="rk"][data-value]')
        rank_match = re.search(
            r"\d+",
            rank_element.get("data-value", "") if rank_element else "",
        )
        if rank_match is None:
            rank_match = re.search(r"\b(\d+)\.?\b", tr.get_text(" ", strip=True))
        rank = int(rank_match.group()) if rank_match else len(rows) + 1

        year_element = tr.select_one(".secondaryInfo")
        year_match = re.search(
            r"\b(?:18|19|20)\d{2}\b",
            year_element.get_text(" ", strip=True) if year_element else "",
        )

        rating_element = tr.select_one('[name="ir"][data-value]')
        if rating_element is None:
            rating_element = tr.select_one('[itemprop="ratingValue"]')

        votes_element = tr.select_one('[name="nv"][data-value]')
        if votes_element is None:
            votes_element = tr.select_one('[itemprop="ratingCount"]')

        rows.append({
            "snapshot": snapshot,
            "rank": rank,
            "title": clean_title(title_link),
            "year": year_match.group() if year_match else "",
            "imdb_id": title_id(title_url),
            "title_url": title_url,
            "rating": attribute_value(rating_element),
            "votes": attribute_value(votes_element),
            "source_file": str(source),
        })

    unique = {}
    for row in sorted(rows, key=lambda item: int(item["rank"])):
        unique.setdefault(int(row["rank"]), row)
    return [unique[rank] for rank in sorted(unique)][:250]


def parse_detailed_results(soup, source):
    rows = []
    for tr in soup.select("tr.detailed"):
        rank_match = re.search(
            r"\d+",
            tr.select_one(".number").get_text(" ", strip=True)
            if tr.select_one(".number")
            else "",
        )
        title_cell = tr.select_one(".title")
        title_link = title_cell.select_one("a[href]") if title_cell else None
        if rank_match is None or title_link is None:
            continue

        title_url = title_link.get("href", "")
        year_element = tr.select_one(".year_type")
        year_match = re.search(
            r"\d{4}",
            year_element.get_text(" ", strip=True) if year_element else "",
        )
        rating_cell = tr.select_one(".imdb_rating")
        rating = ""
        votes = ""
        if rating_cell:
            rating_text = rating_cell.get_text(" ", strip=True)
            rating_match = re.search(r"\d+(?:\.\d+)?", rating_text)
            if rating_match:
                rating = rating_match.group()
            votes_element = rating_cell.select_one("div")
            if votes_element:
                votes = votes_element.get_text(" ", strip=True)

        rows.append({
            "snapshot": snapshot_name(source),
            "rank": int(rank_match.group()),
            "title": clean_title(title_link),
            "year": year_match.group() if year_match else "",
            "imdb_id": title_id(title_url),
            "title_url": title_url,
            "rating": rating,
            "votes": votes,
            "source_file": str(source),
        })
    return sorted(rows, key=lambda row: int(row["rank"]))[:250]


def parse_table_rows(soup, source):
    for table in soup.find_all("table"):
        table_rows = table.find_all("tr")
        if not table_rows:
            continue

        header_row = None
        headers = None
        columns = None
        for tr in table_rows:
            cells = tr.find_all(["th", "td"], recursive=False)
            candidate_headers = [
                cell.get_text(" ", strip=True).lower()
                for cell in cells
            ]
            normalized = [" ".join(header.split()) for header in candidate_headers]
            if (
                any(header == "rank" or header.startswith("rank ") for header in normalized)
                and any(header == "title" or "title" in header for header in normalized)
                and any(header == "rating" or "rating" in header for header in normalized)
            ):
                header_row = tr
                headers = normalized
                break

        if header_row is None:
            continue

        def find_column(names):
            for index, header in enumerate(headers):
                if any(name in header for name in names):
                    return index
            return None

        rank_column = find_column(("rank",))
        title_column = find_column(("title",))
        rating_column = find_column(("rating",))
        votes_column = find_column(("votes",))
        if (
            title_column is None
            or rank_column is None
            or rating_column is None
            or votes_column is None
        ):
            continue

        rows = []
        started = False
        for tr in table_rows:
            if tr is header_row:
                started = True
                continue
            if not started:
                continue
            cells = tr.find_all(["th", "td"], recursive=False)
            needed = max(
                index
                for index in (rank_column, title_column, rating_column, votes_column)
                if index is not None
            )
            if len(cells) <= needed:
                continue

            title_link = next(
                (
                    link
                    for link in cells[title_column].select("a[href]")
                    if title_id(link.get("href", ""))
                ),
                None,
            )
            if title_link is None:
                continue

            rank_match = re.search(r"\d+", cells[rank_column].get_text(" ", strip=True))
            if rank_match is None:
                continue
            title_url = title_link.get("href", "")
            title_text = cells[title_column].get_text(" ", strip=True)
            year_match = re.search(r"\b(?:18|19|20)\d{2}\b", title_text)
            rows.append({
                "snapshot": snapshot_name(source),
                "rank": int(rank_match.group()),
                "title": title_link.get_text(" ", strip=True),
                "year": year_match.group() if year_match else "",
                "imdb_id": title_id(title_url),
                "title_url": title_url,
                "rating": cells[rating_column].get_text(" ", strip=True),
                "votes": (
                    cells[votes_column].get_text(" ", strip=True)
                    if votes_column is not None
                    else ""
                ),
                "source_file": str(source),
            })

        if rows:
            return sorted(rows, key=lambda row: int(row["rank"]))[:250]
    return []


def parse_html(source):
    soup = BeautifulSoup(
        source.read_text(encoding="utf-8", errors="replace"),
        "html.parser",
    )
    rows = parse_json_ld(soup, source)
    if not rows:
        rows = parse_detailed_results(soup, source)
    if not rows:
        rows = parse_table_rows(soup, source)
    if not rows:
        rows = parse_modern_rows(soup, source)
    return rows


def convert(source):
    rows = parse_html(source)
    if not rows:
        print(f"WARNING: no chart rows recognized; skipped {source}")
        return

    output = source.with_suffix(".csv")
    with output.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} rows: {output}")


def merge_csvs(output="imdb_top_250_merged.csv"):
    files = sorted(Path(".").glob("*_top_250/*_top_250.csv"))
    merged_fields = [
        "snapshot",
        "snapshot_date",
        "snapshot_year",
        "rank",
        "title",
        "year",
        "imdb_id",
        "title_url",
        "rating",
        "votes",
        "source_file",
    ]
    rows = []
    for path in files:
        with path.open("r", newline="", encoding="utf-8") as file:
            rows.extend(csv.DictReader(file))

    with open(output, "w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=merged_fields)
        writer.writeheader()
        for row in rows:
            snapshot = row.get("snapshot", "")
            date = (
                f"{snapshot[:4]}-{snapshot[4:6]}-{snapshot[6:8]} "
                f"{snapshot[8:10]}:{snapshot[10:12]}:{snapshot[12:14]}"
                if len(snapshot) == 14 and snapshot.isdigit()
                else ""
            )
            writer.writerow({
                "snapshot": snapshot,
                "snapshot_date": date,
                "snapshot_year": snapshot[:4] if snapshot else "",
                "rank": row.get("rank", ""),
                "title": row.get("title", ""),
                "year": row.get("year", ""),
                "imdb_id": row.get("imdb_id", ""),
                "title_url": row.get("title_url", ""),
                "rating": row.get("rating", ""),
                "votes": row.get("votes", ""),
                "source_file": row.get("source_file", ""),
            })
    print(f"Merged {len(rows)} rows: {output}")


if __name__ == "__main__":
    for folder in sorted(Path(".").glob("*_top_250")):
        for html_file in sorted(folder.glob("*_top_250.html")):
            convert(html_file)
    merge_csvs()
