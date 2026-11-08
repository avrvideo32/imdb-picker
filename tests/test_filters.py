import unittest

import duckdb

from filters import build_where


class GenreFilterTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect(":memory:")
        self.con.execute(
            """
            CREATE TABLE titles (
                tconst VARCHAR,
                primaryTitle VARCHAR,
                originalTitle VARCHAR,
                titleType VARCHAR,
                startYear VARCHAR,
                runtimeMinutes VARCHAR,
                averageRating VARCHAR,
                numVotes VARCHAR,
                genres VARCHAR,
                isAdult INTEGER
            )
            """
        )
        self.con.executemany(
            "INSERT INTO titles VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ("tt0000001", "Drama comedy", "Drama comedy", "movie", "2000", "100", "7.0", "100", "Drama,Comedy", 0),
                ("tt0000002", "Award winner", "Award winner", "movie", "2001", "100", "7.0", "100", "Award", 0),
                ("tt0000003", "Action comedy", "Action comedy", "movie", "2002", "100", "7.0", "100", "Action,Comedy", 0),
                ("tt0000004", "Action drama", "Action drama", "movie", "2003", "100", "7.0", "100", "Action,Drama", 0),
                ("tt0000005", "Comedy action", "Comedy action", "movie", "2004", "100", "7.0", "100", "Comedy,Action", 0),
            ],
        )

    def tearDown(self):
        self.con.close()

    def query_ids(self, selected, mode="Any selected genre", excluded=None):
        values = {
            "min_votes": "0",
            "min_rating": "0",
            "year": "",
            "decade": "Any",
            "runtime_min": "0",
            "runtime_max": "3000",
            "adult": True,
            "genre_match": mode,
            "excluded_genres": excluded or [],
            "search": "",
        }
        genres = {
            "Action": "Action" in selected,
            "Comedy": "Comedy" in selected,
        }
        where, params = build_where(values, genres, {"movie": True})
        rows = self.con.execute(
            f"SELECT tconst FROM titles WHERE {where} ORDER BY tconst", params
        ).fetchall()
        return [row[0] for row in rows]

    def test_genre_at_end_of_list_is_matched(self):
        self.assertEqual(
            self.query_ids(["Comedy"]),
            ["tt0000001", "tt0000003", "tt0000005"],
        )

    def test_any_selected_genre_uses_or(self):
        self.assertEqual(
            self.query_ids(["Action", "Comedy"]),
            [
                "tt0000001", "tt0000003", "tt0000004", "tt0000005"
            ],
        )

    def test_all_selected_genres_uses_and(self):
        self.assertEqual(
            self.query_ids(["Action", "Comedy"], mode="All selected genres"),
            ["tt0000003", "tt0000005"],
        )

    def test_excluded_genre_at_end_of_list_is_excluded(self):
        self.assertEqual(
            self.query_ids([], excluded=["Comedy"]),
            ["tt0000002", "tt0000004"],
        )


if __name__ == "__main__":
    unittest.main()
