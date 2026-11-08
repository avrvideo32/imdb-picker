import csv
import io
import re


def parse_watched_csv(raw_bytes):
    """Extract IMDb title IDs from an IMDb-export-style CSV."""
    try:
        csv_text = raw_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("The CSV must be UTF-8 encoded.") from exc

    reader = csv.DictReader(io.StringIO(csv_text))
    if not reader.fieldnames:
        raise ValueError("The CSV is empty or has no header row.")

    columns = {
        str(column).lstrip("\ufeff").strip().casefold(): column
        for column in reader.fieldnames
        if column is not None
    }
    id_column = None
    for candidate in ("const", "tconst", "imdb id", "imdb_id", "title id", "title_id"):
        if candidate in columns:
            id_column = columns[candidate]
            break

    if id_column is None:
        raise ValueError(
            "Couldn't find an IMDb ID column. IMDb exports normally call it 'Const'."
        )

    ids = set()
    for row in reader:
        match = re.search(r"tt\d+", str(row.get(id_column, "")))
        if match:
            ids.add(match.group(0))

    if not ids:
        raise ValueError("No IMDb title IDs (for example, tt0111161) were found.")
    return sorted(ids)
