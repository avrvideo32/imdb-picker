RESULT_COLUMNS = """
    tconst,
    primaryTitle,
    COALESCE(NULLIF(startYear, '\\N'), 'N/A') AS startYear,
    COALESCE(NULLIF(genres, '\\N'), 'No Genre') AS genres,
    titleType,
    NULLIF(runtimeMinutes, '\\N') AS runtimeMinutes,
    averageRating,
    numVotes
"""

SORT_OPTIONS = {
    "Votes (Most Popular)": "TRY_CAST(numVotes AS BIGINT) DESC NULLS LAST",
    "Keep them Random": "random()",
    "Rating (High to Low)": "TRY_CAST(averageRating AS DOUBLE) DESC NULLS LAST",
    "Rating (Low to High)": "TRY_CAST(averageRating AS DOUBLE) ASC NULLS LAST",
    "Year (Newest)": "TRY_CAST(startYear AS INT) DESC NULLS LAST",
    "Year (Oldest)": "TRY_CAST(startYear AS INT) ASC NULLS LAST",
    "Runtime (Longest)": "TRY_CAST(runtimeMinutes AS INT) DESC NULLS LAST",
    "Runtime (Shortest)": "TRY_CAST(runtimeMinutes AS INT) ASC NULLS LAST",
    "Title (A-Z)": "primaryTitle ASC NULLS LAST",
}


def add_exclusions(where, params, watched_ids=None, excluded_ids=None):
    """Append safe, parameterized IMDb-ID exclusions to a WHERE clause."""
    clauses = [where]
    query_params = list(params)

    watched_ids = sorted(set(watched_ids or []))
    if watched_ids:
        clauses.append("tconst NOT IN (SELECT UNNEST(?))")
        query_params.append(watched_ids)

    excluded_ids = sorted(set(excluded_ids or []))
    if excluded_ids:
        placeholders = ", ".join("?" for _ in excluded_ids)
        clauses.append(f"tconst NOT IN ({placeholders})")
        query_params.extend(excluded_ids)

    return " AND ".join(f"({clause})" for clause in clauses), query_params


def build_selection_query(where, sort_by, num_picks, generation_mode):
    """Build SQL for standard random sampling or popularity-balanced discovery."""
    order_clause = SORT_OPTIONS[sort_by]

    if generation_mode == "Discovery":
        # NTILE divides the filtered pool into four similarly sized popularity
        # bands. Round-robin sampling mixes lesser-known and widely rated titles.
        return f"""
            WITH candidates AS (
                SELECT
                    {RESULT_COLUMNS},
                    NTILE(4) OVER (
                        ORDER BY TRY_CAST(numVotes AS BIGINT) ASC NULLS FIRST
                    ) AS popularity_band
                FROM movie_view
                WHERE {where}
            ),
            shuffled AS (
                SELECT *, random() AS shuffle_key
                FROM candidates
            ),
            randomized AS (
                SELECT
                    *,
                    ROW_NUMBER() OVER (
                        PARTITION BY popularity_band
                        ORDER BY shuffle_key
                    ) AS band_position
                FROM shuffled
            ),
            random_batch AS (
                SELECT
                    tconst, primaryTitle, startYear, genres,
                    titleType, runtimeMinutes, averageRating, numVotes
                FROM randomized
                ORDER BY band_position, popularity_band
                LIMIT ?
            )
            SELECT *
            FROM random_batch
            ORDER BY {order_clause}
        """

    if sort_by == "Keep them Random":
        return f"""
            SELECT {RESULT_COLUMNS}
            FROM movie_view
            WHERE {where}
            ORDER BY random()
            LIMIT ?
        """

    return f"""
        WITH random_batch AS (
            SELECT {RESULT_COLUMNS}
            FROM movie_view
            WHERE {where}
            ORDER BY random()
            LIMIT ?
        )
        SELECT *
        FROM random_batch
        ORDER BY {order_clause}
    """
