# CSE241-Group-Project

## Scrape archived IMDb title pages

Run `scrape_imdb_descriptions.ipynb`, execute its dependency cell, and adjust
`LIMIT` to process the first movie ID in `imdb_ids_with_titles.csv` (default:
1). Set `LIMIT = 0` to process every ID. The CDX capture list is fetched
through Tor, then Selenium uses the Tor proxy to try captures newest-first
until one succeeds. The capture list is saved to
`responses/response_<imdb_id>.txt`, the successful timestamp to
`responses/exact_dates_<imdb_id>.csv`, and only the latest successful HTML to
`descriptions/<imdb_id>.html`.

For command-line use, install `requests[socks]` and `selenium`, ensure Tor is
listening on `127.0.0.1:9050`, then run
`python3 scrape_imdb_descriptions.py --limit 1`; use `--limit 0` for every ID.