# CSE241 IMDb Top 250 Project

This project collects and analyzes historical IMDb Top 250 movie data.
It builds a dataset of rankings, ratings, vote counts, movie
metadata, descriptions, and archived snapshot dates from 2005 to 2025.

## What It Does

- Retrieves archived IMDb Top 250 pages through Tor
- Parses movie ranks, titles, ratings, vote counts, and IMDb IDs
- Downloads archived title descriptions and ratings
- Combines snapshots into CSV datasets
- Joins descriptions with ranking and ratings data
- Provides exploratory analysis in `EDA.ipynb`

## Repository Contents

- `*_top_250/` - archived HTML snapshots and parsed CSV files
- `imdb_top_250_merged.csv` - all ranking snapshots combined
- `imdb_ratings.csv` and `imdb_descriptions.csv` - movie-level data
- `imdb_ratings_with_descriptions.csv` - ratings joined with descriptions
- `imdb_top_250_with_descriptions.csv` - rankings joined with descriptions
- `parse_top250_html.py` - parses and merges Top 250 HTML snapshots
- `join_movie_descriptions.py` - joins descriptions into the merged datasets
- `EDA.ipynb` - exploratory data analysis
