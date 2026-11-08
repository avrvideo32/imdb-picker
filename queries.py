import random
from collections import Counter, defaultdict


RESULT_COLUMNS = """
    tconst,
    primaryTitle,
    COALESCE(NULLIF(startYear, '\\N'), 'N/A') AS startYear,
    COALESCE(NULLIF(genres, '\\N'), 'No Genre') AS genres,
    titleType,
    NULLIF(runtimeMinutes, '\\N') AS runtimeMinutes,
    averageRating,
    numVotes,
    originalTitleRegion,
    originalTitleLanguage
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

# These dimensions are intentionally weighted rather than combined into one
# giant Cartesian group. It lets a title contribute to several genres while
# still balancing years, rating, popularity and available origin metadata.
DIVERSITY_WEIGHTS = {
    "popularity": 1.0,
    "rating": 1.0,
    "decade": 1.2,
    "genre": 1.5,
    "region": 1.0,
    "language": 0.8,
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
    """Build either a standard random query or a Discovery candidate-pool query."""
    order_clause = SORT_OPTIONS[sort_by]

    if generation_mode == "Discovery":
        # Calculate quantile labels over the complete filtered pool before
        # drawing a bounded random candidate pool for the diversity selector.
        return f"""
            WITH eligible AS (
                SELECT
                    {RESULT_COLUMNS},
                    NTILE(4) OVER (
                        ORDER BY TRY_CAST(numVotes AS BIGINT) ASC NULLS FIRST
                    ) AS popularity_band,
                    NTILE(4) OVER (
                        ORDER BY TRY_CAST(averageRating AS DOUBLE) ASC NULLS LAST
                    ) AS rating_band
                FROM movie_view
                WHERE {where}
            )
            SELECT *
            FROM eligible
            ORDER BY random()
            LIMIT ?
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


def _clean_category(value, fallback="Unknown"):
    if value is None:
        return fallback
    value = str(value).strip()
    if not value or value.casefold() in {"nan", "none", r"\n", "n/a", "no genre"}:
        return fallback
    return value


def _row_features(row):
    """Return the diversity categories represented by one IMDb title row."""
    year = _clean_category(row.get("startYear"))
    if year.isdigit() and len(year) == 4:
        decade = f"{(int(year) // 10) * 10}s"
    else:
        decade = "Unknown"

    raw_genres = _clean_category(row.get("genres"))
    if raw_genres == "Unknown":
        genres = ("Unknown",)
    else:
        genres = tuple(
            dict.fromkeys(
                genre.strip()
                for genre in raw_genres.split(",")
                if genre.strip()
            )
        ) or ("Unknown",)

    try:
        popularity = f"Q{int(row.get('popularity_band'))}"
    except (TypeError, ValueError):
        popularity = "Unknown"

    try:
        rating = f"Q{int(row.get('rating_band'))}"
    except (TypeError, ValueError):
        rating = "Unknown"

    return {
        "popularity": (popularity,),
        "rating": (rating,),
        "decade": (decade,),
        "genre": genres,
        "region": (_clean_category(row.get("originalTitleRegion")).upper(),),
        "language": (_clean_category(row.get("originalTitleLanguage")).lower(),),
    }


def select_diverse_picks(candidates, num_picks, diversity_strength=80):
    """
    Greedily choose titles that cover underrepresented categories.

    Each selected title updates popularity, rating, decade, genre, original
    title region and IMDb AKA language counts. Genre contributes all
    IMDb genre tags but only its least-represented tag determines the score.
    """
    remaining = [dict(row) for row in candidates]
    if not remaining or num_picks <= 0:
        return []

    strength = max(0.0, min(100.0, float(diversity_strength))) / 100.0
    feature_map = {id(row): _row_features(row) for row in remaining}
    selected = []
    counts = defaultdict(Counter)
    total_weight = sum(DIVERSITY_WEIGHTS.values())

    while remaining and len(selected) < num_picks:
        best_index = None
        best_score = None

        for index, row in enumerate(remaining):
            features = feature_map[id(row)]
            balance_cost = 0.0

            for dimension, weight in DIVERSITY_WEIGHTS.items():
                categories = features[dimension]
                # For multi-genre titles, score against the least represented
                # genre so a title can help fill a gap in the current batch.
                category_cost = min(counts[dimension][category] for category in categories)
                balance_cost += weight * category_cost

            balance_cost /= total_weight
            score = strength * balance_cost + (1.0 - strength) * random.random()

            if best_score is None or score < best_score:
                best_score = score
                best_index = index

        chosen = remaining.pop(best_index)
        selected.append(chosen)

        for dimension, categories in feature_map[id(chosen)].items():
            for category in categories:
                counts[dimension][category] += 1

    return selected


def sort_picks(rows, sort_by):
    """Apply the UI sort option to an already selected Discovery batch."""
    rows = [dict(row) for row in rows]
    if sort_by == "Keep them Random":
        random.shuffle(rows)
        return rows

    numeric_columns = {
        "Votes (Most Popular)": ("numVotes", True),
        "Rating (High to Low)": ("averageRating", True),
        "Rating (Low to High)": ("averageRating", False),
        "Year (Newest)": ("startYear", True),
        "Year (Oldest)": ("startYear", False),
        "Runtime (Longest)": ("runtimeMinutes", True),
        "Runtime (Shortest)": ("runtimeMinutes", False),
    }

    if sort_by == "Title (A-Z)":
        return sorted(rows, key=lambda row: str(row.get("primaryTitle") or "").casefold())

    column, descending = numeric_columns.get(
        sort_by, ("numVotes", True)
    )

    def sort_key(row):
        try:
            value = float(row.get(column))
        except (TypeError, ValueError):
            return (1, 0.0)
        return (0, -value if descending else value)

    return sorted(rows, key=sort_key)
