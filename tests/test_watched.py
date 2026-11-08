import unittest

from watched import parse_watched_csv


class WatchedCsvTests(unittest.TestCase):
    def test_reads_standard_imdb_const_column(self):
        raw = (
            b"Const,Your Rating,Title\n"
            b"tt0111161,9,The Shawshank Redemption\n"
            b"tt0068646,10,The Godfather\n"
        )
        self.assertEqual(
            parse_watched_csv(raw),
            ["tt0068646", "tt0111161"],
        )

    def test_accepts_bom_and_imdb_title_urls(self):
        raw = (
            b"\xef\xbb\xbfIMDb ID,Title\n"
            b"https://www.imdb.com/title/tt0111161/,Example\n"
        )
        self.assertEqual(parse_watched_csv(raw), ["tt0111161"])

    def test_requires_a_title_id_column(self):
        with self.assertRaisesRegex(ValueError, "Const"):
            parse_watched_csv(b"Title,Year\nExample,2020\n")


if __name__ == "__main__":
    unittest.main()
