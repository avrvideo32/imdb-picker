import itertools
import unittest

import duckdb

from queries import (
    add_exclusions,
    build_selection_query,
    select_diverse_picks,
    sort_picks,
)


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.con = duckdb.connect(":memory:")
        self.con.execute(
            """
            CREATE TABLE movie_view (
                tconst VARCHAR,
                primaryTitle VARCHAR,
                startYear VARCHAR,
                genres VARCHAR,
                titleType VARCHAR,
                runtimeMinutes VARCHAR,
                averageRating VARCHAR,
                numVotes VARCHAR,
                originalTitleRegion VARCHAR,
                originalTitleLanguage VARCHAR
            )
            """
        )
        rows = [
            (
                f"tt000000{i}", f"Title {i}", "2000", "Drama", "movie",
                "100", "7.0", str(i * 10), "US", "en"
            )
            for i in range(1, 9)
        ]
        self.con.executemany(
            "INSERT INTO movie_view VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )

    def tearDown(self):
        self.con.close()

    def test_discovery_query_computes_popularity_and_rating_quartiles(self):
        sql = build_selection_query(
            "1=1", "Votes (Most Popular)", 8, "Discovery"
        )
        rows = self.con.execute(sql, [8]).fetchall()

        self.assertEqual(len(rows), 8)
        # The final two columns are the independently calculated quartiles.
        self.assertEqual({row[-2] for row in rows}, {1, 2, 3, 4})
        self.assertEqual({row[-1] for row in rows}, {1, 2, 3, 4})

    def test_standard_mode_returns_requested_number_of_unique_picks(self):
        sql = build_selection_query(
            "1=1", "Keep them Random", 3, "Standard Random"
        )
        rows = self.con.execute(sql, [3]).fetchall()
        self.assertEqual(len(rows), 3)
        self.assertEqual(len({row[0] for row in rows}), 3)

    def test_watched_ids_and_existing_picks_are_excluded(self):
        where, params = add_exclusions(
            "1=1",
            [],
            watched_ids=["tt0000001", "tt0000002"],
            excluded_ids=["tt0000003"],
        )
        rows = self.con.execute(
            f"SELECT tconst FROM movie_view WHERE {where} ORDER BY tconst",
            params,
        ).fetchall()
        self.assertEqual(
            [row[0] for row in rows],
            [
                "tt0000004", "tt0000005", "tt0000006",
                "tt0000007", "tt0000008",
            ],
        )

    def test_diversity_selector_spreads_all_available_dimensions(self):
        candidates = []
        index = 0
        # Build a balanced synthetic pool where the dimensions can vary
        # independently, so the selector has no trade-off forced by the data.
        combinations = itertools.product(
            range(1, 5),
            range(1, 5),
            (1980, 2000),
            ("Drama", "Comedy"),
            ("US", "FR"),
            ("en", "fr"),
        )
        for popularity, rating, year, genre, region, language in combinations:
            index += 1
            candidates.append(
                {
                    "tconst": f"tt{index:07d}",
                    "primaryTitle": f"Title {index}",
                    "startYear": str(year),
                    "genres": genre,
                    "numVotes": str(index * 100),
                    "averageRating": str(5 + rating),
                    "popularity_band": popularity,
                    "rating_band": rating,
                    "originalTitleRegion": region,
                    "originalTitleLanguage": language,
                }
            )

        picks = select_diverse_picks(candidates, 8, diversity_strength=100)
        self.assertEqual(len(picks), 8)
        self.assertEqual(len({pick["tconst"] for pick in picks}), 8)
        self.assertTrue(all(pick.get("_discovery_reason") for pick in picks))
        self.assertEqual(
            {pick["popularity_band"] for pick in picks}, {1, 2, 3, 4}
        )
        self.assertEqual(
            {pick["rating_band"] for pick in picks}, {1, 2, 3, 4}
        )
        self.assertEqual(
            {pick["startYear"] for pick in picks}, {"1980", "2000"}
        )
        self.assertEqual(
            {pick["genres"] for pick in picks}, {"Drama", "Comedy"}
        )
        self.assertEqual(
            {pick["originalTitleRegion"] for pick in picks}, {"US", "FR"}
        )
        self.assertEqual(
            {pick["originalTitleLanguage"] for pick in picks}, {"en", "fr"}
        )

    def test_sorting_applies_after_diverse_selection(self):
        rows = [
            {"primaryTitle": "B", "numVotes": "200"},
            {"primaryTitle": "A", "numVotes": "100"},
        ]
        sorted_rows = sort_picks(rows, "Votes (Most Popular)")
        self.assertEqual(
            [row["primaryTitle"] for row in sorted_rows], ["B", "A"]
        )


if __name__ == "__main__":
    unittest.main()
