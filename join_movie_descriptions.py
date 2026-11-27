import csv
from pathlib import Path


PROJECT_DIR = Path(__file__).resolve().parent
DESCRIPTIONS_CSV = PROJECT_DIR / 'imdb_descriptions.csv'
DATASETS = (
    (PROJECT_DIR / 'imdb_ratings.csv', PROJECT_DIR / 'imdb_ratings_with_descriptions.csv'),
    (PROJECT_DIR / 'imdb_top_250_merged.csv', PROJECT_DIR / 'imdb_top_250_with_descriptions.csv'),
)
DESCRIPTION_MATCH_FIELD = 'description_match'


def read_csv(path):
    with path.open(newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source)
        if not reader.fieldnames:
            raise ValueError(f'{path.name} is empty or has no header row')
        if len(reader.fieldnames) != len(set(reader.fieldnames)):
            raise ValueError(f'{path.name} contains duplicate column names')

        rows = list(reader)
        for line_number, row in enumerate(rows, start=2):
            if None in row:
                raise ValueError(f'{path.name} has extra values on CSV line {line_number}')
        return reader.fieldnames, rows


def normalize_imdb_id(value):
    return (value or '').strip().casefold()


def load_descriptions():
    headers, rows = read_csv(DESCRIPTIONS_CSV)
    if 'imdb_id' not in headers:
        raise ValueError(f'{DESCRIPTIONS_CSV.name} must have an imdb_id column')

    descriptions = {}
    for row_number, row in enumerate(rows, start=2):
        imdb_id = normalize_imdb_id(row.get('imdb_id'))
        if not imdb_id:
            raise ValueError(f'{DESCRIPTIONS_CSV.name} has a missing imdb_id on CSV line {row_number}')
        if imdb_id in descriptions:
            raise ValueError(f'{DESCRIPTIONS_CSV.name} has duplicate movie ID {imdb_id}')
        descriptions[imdb_id] = row

    return headers, descriptions


def write_joined_csv(source_path, output_path, description_headers, descriptions):
    source_headers, source_rows = read_csv(source_path)
    if 'imdb_id' not in source_headers:
        raise ValueError(f'{source_path.name} must have an imdb_id column')
    if DESCRIPTION_MATCH_FIELD in source_headers:
        raise ValueError(
            f'{source_path.name} already has a {DESCRIPTION_MATCH_FIELD} column'
        )

    description_fields = [
        (header, f'description_{header}')
        for header in description_headers
        if header != 'imdb_id'
    ]
    output_headers = [
        *source_headers,
        DESCRIPTION_MATCH_FIELD,
        *(output_name for _, output_name in description_fields),
    ]
    if len(output_headers) != len(set(output_headers)):
        raise ValueError(f'Column name collision while joining {source_path.name}')

    matched_rows = 0
    missing_rows = 0
    missing_ids = set()
    temporary_path = output_path.with_suffix(output_path.suffix + '.tmp')

    try:
        with temporary_path.open('w', newline='', encoding='utf-8') as output:
            writer = csv.DictWriter(output, fieldnames=output_headers, extrasaction='raise')
            writer.writeheader()

            for source_row in source_rows:
                imdb_id = normalize_imdb_id(source_row.get('imdb_id'))
                description = descriptions.get(imdb_id) if imdb_id else None
                joined_row = dict(source_row)
                joined_row[DESCRIPTION_MATCH_FIELD] = 'matched' if description else 'missing'

                if description:
                    matched_rows += 1
                else:
                    missing_rows += 1
                    if imdb_id:
                        missing_ids.add(imdb_id)

                for source_name, output_name in description_fields:
                    joined_row[output_name] = description.get(source_name, '') if description else ''
                writer.writerow(joined_row)

        with temporary_path.open(newline='', encoding='utf-8') as output:
            exported_rows = sum(1 for _ in csv.DictReader(output))
        if exported_rows != len(source_rows):
            raise RuntimeError(
                f'{output_path.name} should contain {len(source_rows)} rows; '
                f'found {exported_rows}'
            )

        temporary_path.replace(output_path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()

    print(
        f'{source_path.name} -> {output_path.name}: '
        f'{exported_rows:,} rows, {matched_rows:,} matched, '
        f'{missing_rows:,} unmatched rows across {len(missing_ids):,} movie IDs'
    )
    if missing_ids:
        print('  IDs without description data:', ', '.join(sorted(missing_ids)))


def main():
    description_headers, descriptions = load_descriptions()
    for source_path, output_path in DATASETS:
        if not source_path.is_file():
            raise FileNotFoundError(f'Input CSV not found: {source_path}')
        write_joined_csv(source_path, output_path, description_headers, descriptions)


if __name__ == '__main__':
    main()
