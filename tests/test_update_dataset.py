import gzip
import tempfile
import unittest
from pathlib import Path

import duckdb

from scripts.update_imdb import create_dataset


def write_gzip(path, content):
    with gzip.open(path, "wt", encoding="utf-8", newline="") as output:
        output.write(content)


class DatasetUpdateTests(unittest.TestCase):
    def test_original_title_region_and_language_are_joined_once_per_title(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            basics = directory / "title.basics.tsv.gz"
            ratings = directory / "title.ratings.tsv.gz"
            akas = directory / "title.akas.tsv.gz"
            parquet = directory / "imdb_cache.parquet"

            write_gzip(
                basics,
                "tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\t"
                "startYear\tendYear\truntimeMinutes\tgenres\n"
                "tt0000001\tmovie\tExample One\tExample One\t0\t2001\t"
                "\\N\t100\tDrama,Comedy\n"
                "tt0000002\ttvMovie\tExample Two\tExample Two\t0\t2002\t"
                "\\N\t90\tDrama\n",
            )
            write_gzip(
                ratings,
                "tconst\taverageRating\tnumVotes\n"
                "tt0000001\t8.2\t1200\n",
            )
            write_gzip(
                akas,
                "titleId\tordering\ttitle\tregion\tlanguage\ttypes\t"
                "attributes\tisOriginalTitle\n"
                "tt0000001\t1\tExample One\tUS\ten\toriginal\t\\N\t1\n"
                "tt0000001\t2\tExample One\tGB\ten\timdbDisplay\t\\N\t0\n"
                "tt0000002\t1\tExample Two\tFR\tfr\toriginal\t\\N\t1\n",
            )

            create_dataset(basics, ratings, akas, parquet)

            con = duckdb.connect()
            try:
                rows = con.execute(
                    """
                    SELECT tconst, originalTitleRegion, originalTitleLanguage
                    FROM read_parquet(?)
                    ORDER BY tconst
                    """,
                    [str(parquet)],
                ).fetchall()
            finally:
                con.close()

            self.assertEqual(
                rows,
                [
                    ("tt0000001", "US", "en"),
                    ("tt0000002", "FR", "fr"),
                ],
            )


if __name__ == "__main__":
    unittest.main()
