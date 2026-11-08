import unittest

import duckdb

from queries import add_exclusions, build_selection_query


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
                numVotes VARCHAR
            )
            """
        )
        rows = [
            (f"tt000000{i}", f"Title {i}", "2000", "Drama", "movie", "100", "7.0", str(i * 10))
            for i in range(1, 9)
        ]
        self.con.executemany(
            "INSERT INTO movie_view VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows
        )

    def tearDown(self):
        self.con.close()

    def test_discovery_samples_across_popularity_quartiles(self):
        sql = build_selection_query(
            "1=1", "Votes (Most Popular)", 4, "Discovery"
        )
        rows = self.con.execute(sql, [4]).fetchall()
        votes = sorted(int(row[7]) for row in rows)

        self.assertEqual(len(rows), 4)
        self.assertEqual(len({row[0] for row in rows}), 4)
        # Eight rows form four two-title quartiles; four picks should contain
        # one item from each quartile.
        self.assertTrue(10 <= votes[0] <= 20)
        self.assertTrue(30 <= votes[1] <= 40)
        self.assertTrue(50 <= votes[2] <= 60)
        self.assertTrue(70 <= votes[3] <= 80)

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


if __name__ == "__main__":
    unittest.main()
