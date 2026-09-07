def build_where(values, genres, types):
    """Build a parameterized DuckDB WHERE clause and its parameters."""
    clauses = []
    params = []

    def add(condition, value):
        clauses.append(condition)
        params.append(value)

    if values.get("min_votes"):
        add("TRY_CAST(numVotes AS BIGINT) >= ?", int(values["min_votes"]))

    if values.get("min_rating"):
        add("TRY_CAST(averageRating AS DOUBLE) >= ?", float(values["min_rating"]))

    year = values.get("year", "").strip()
    if year:
        add("TRY_CAST(startYear AS INT) = ?", int(year))

    decade = values.get("decade", "Any")
    if decade != "Any":
        start = int(decade)
        clauses.append("TRY_CAST(startYear AS INT) BETWEEN ? AND ?")
        params.extend([start, start + 9])

    if values.get("runtime_min"):
        add("TRY_CAST(runtimeMinutes AS INT) >= ?", int(values["runtime_min"]))

    if values.get("runtime_max"):
        add("TRY_CAST(runtimeMinutes AS INT) <= ?", int(values["runtime_max"]))

    selected_types = [title_type for title_type, enabled in types.items() if enabled]
    if selected_types:
        placeholders = ", ".join("?" for _ in selected_types)
        clauses.append(f"titleType IN ({placeholders})")
        params.extend(selected_types)

    # IMDb's genre field is a comma-separated string. Matching comma-delimited
    # values avoids accidental substring matches such as "War" vs "Award".
    selected_genres = [genre for genre, enabled in genres.items() if enabled]
    for genre in selected_genres:
        clauses.append(
            "(genres = ? OR genres LIKE ? OR genres LIKE ?)"
        )
        params.extend([genre, f"{genre},%", f"%,{genre},%"])

    for genre in values.get("excluded_genres", []):
        clauses.append(
            "NOT (genres = ? OR genres LIKE ? OR genres LIKE ?)"
        )
        params.extend([genre, f"{genre},%", f"%,{genre},%"])

    if not values.get("adult", False):
        clauses.append("TRY_CAST(isAdult AS INT) = 0")

    search = values.get("search", "").strip()
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
            clauses.append(
                "(primaryTitle ILIKE ? OR originalTitle ILIKE ?)"
            )
            params.extend([f"%{search}%", f"%{search}%"])

    return (" AND ".join(clauses) if clauses else "1=1"), params
