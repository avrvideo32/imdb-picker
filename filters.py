def build_where(values, genres, types):
    """Build a parameterized DuckDB WHERE clause and its parameters."""
    clauses = []
    params = []

    def add(condition, value):
        clauses.append(condition)
        params.append(value)

    if values.get("min_votes") not in (None, ""):
        add("TRY_CAST(numVotes AS BIGINT) >= ?", int(values["min_votes"]))

    if values.get("min_rating") not in (None, ""):
        add("TRY_CAST(averageRating AS DOUBLE) >= ?", float(values["min_rating"]))

    year = str(values.get("year", "")).strip()
    if year:
        add("TRY_CAST(startYear AS INT) = ?", int(year))

    decade = values.get("decade", "Any")
    if decade != "Any":
        start = int(decade)
        clauses.append("TRY_CAST(startYear AS INT) BETWEEN ? AND ?")
        params.extend([start, start + 9])

    if values.get("runtime_min") not in (None, ""):
        add("TRY_CAST(runtimeMinutes AS INT) >= ?", int(values["runtime_min"]))

    if values.get("runtime_max") not in (None, ""):
        add("TRY_CAST(runtimeMinutes AS INT) <= ?", int(values["runtime_max"]))

    selected_types = [title_type for title_type, enabled in types.items() if enabled]
    if selected_types:
        placeholders = ", ".join("?" for _ in selected_types)
        clauses.append(f"titleType IN ({placeholders})")
        params.extend(selected_types)

    # IMDb stores genres as comma-separated tokens. Split the field into a
    # list so a genre is matched exactly, including when it is the final token.
    selected_genres = [genre for genre, enabled in genres.items() if enabled]
    if selected_genres:
        genre_expr = "list_contains(string_split(COALESCE(genres, ''), ','), ?)"
        if values.get("genre_match", "Any selected genre") == "All selected genres":
            for genre in selected_genres:
                clauses.append(genre_expr)
                params.append(genre)
        else:
            clauses.append("(" + " OR ".join(genre_expr for _ in selected_genres) + ")")
            params.extend(selected_genres)

    for genre in values.get("excluded_genres", []):
        clauses.append(
            "NOT list_contains(string_split(COALESCE(genres, ''), ','), ?)"
        )
        params.append(genre)

    if not values.get("adult", False):
        clauses.append("TRY_CAST(isAdult AS INT) = 0")

    search = str(values.get("search", "")).strip()
    if search:
        lowered = search.lower()
        if values.get("fuzzy", False):
            clauses.append(
                "("
                "jaro_winkler_similarity(lower(primaryTitle), ?) >= ? "
                "OR jaro_winkler_similarity(lower(originalTitle), ?) >= ?"
                ")"
            )
            params.extend([lowered, 0.70, lowered, 0.70])
        else:
            clauses.append("(primaryTitle ILIKE ? OR originalTitle ILIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

    return (" AND ".join(clauses) if clauses else "1=1"), params
