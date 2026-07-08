def build_where(values, selected_genres, selected_types):
    clauses = []
    params = []

    if values.get('min_votes'):
        clauses.append("numVotes >= ?")
        params.append(int(values['min_votes']))

    if values.get('min_rating'):
        clauses.append("averageRating >= ?")
        params.append(float(values['min_rating']))

    if values.get('year'):
        clauses.append("startYear = ?")
        params.append(str(values['year']))

    if values.get('decade', 'Any') != 'Any':
        d = int(values['decade'])
        # TRY_CAST prevents crashes if startYear contains '\N' or empty strings
        clauses.append(f"TRY_CAST(startYear AS INT) BETWEEN {d} AND {d + 9}")

    if values.get('runtime_min'):
        clauses.append("TRY_CAST(runtimeMinutes AS INT) >= ?")
        params.append(int(values['runtime_min']))

    if values.get('runtime_max'):
        clauses.append("TRY_CAST(runtimeMinutes AS INT) <= ?")
        params.append(int(values['runtime_max']))

    if selected_types:
        placeholders = ", ".join(["?"] * len(selected_types))
        clauses.append(f"titleType IN ({placeholders})")
        params.extend(selected_types)

    if selected_genres:
        genre_clauses = []
        for g in selected_genres:
            genre_clauses.append("genres LIKE ?")
            params.append(f"%{g}%")
        clauses.append("(" + " AND ".join(genre_clauses) + ")")

    excluded_genres = values.get('excluded_genres', [])
    if excluded_genres:
        exclude_clauses = []
        for g in excluded_genres:
            exclude_clauses.append("genres NOT LIKE ?")
            params.append(f"%{g}%")
        clauses.append("(" + " AND ".join(exclude_clauses) + ")")

    if not values.get('adult', False):
        clauses.append("isAdult = 0")

    search = values.get('search', '').strip()
    if search:
        if values.get('fuzzy', False):
            clauses.append("(jaro_winkler_similarity(lower(primaryTitle), ?) > 0.7 OR "
                           "jaro_winkler_similarity(lower(originalTitle), ?) > 0.7)")
            params.extend([search.lower(), search.lower()])
        else:
            clauses.append("(primaryTitle ILIKE ? OR originalTitle ILIKE ?)")
            params.extend([f"%{search}%", f"%{search}%"])

    where_sql = ' AND '.join(clauses) if clauses else '1=1'
    return where_sql, params
