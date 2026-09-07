import html
import json
import os
from pathlib import Path

import duckdb
import streamlit as st

from filters import build_where
from utils import (
    GENRES,
    TITLE_TYPES,
    DEFAULT_TYPES,
    DECADES,
    TYPE_MAP,
    format_runtime,
    format_votes,
    format_rating,
)

st.set_page_config(page_title="IMDb Picker", page_icon="🎬", layout="centered")

DATASET_URL = (
    "https://huggingface.co/datasets/Avrozavr/Imdb/"
    "resolve/main/imdb_cache.parquet"
)
DEFAULTS_FILE = Path(__file__).with_name("user_defaults.json")

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

DEFAULT_KEYS = [
    "min_votes", "min_rating", "runtime_min", "runtime_max",
    "decade", "year", "search", "fuzzy", "adult",
    "selected_types", "selected_genres", "excluded_genres",
]


def load_defaults():
    try:
        if DEFAULTS_FILE.exists():
            data = json.loads(DEFAULTS_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        pass
    return {}


def save_defaults(data):
    tmp = DEFAULTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, DEFAULTS_FILE)


if "initialized" not in st.session_state:
    saved = load_defaults()
    for key in DEFAULT_KEYS:
        if key in saved:
            st.session_state[key] = saved[key]
    st.session_state.initialized = True


@st.cache_resource(show_spinner=False)
def get_connection():
    con = duckdb.connect(":memory:")
    try:
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
    except Exception:
        # httpfs may already be bundled/loaded depending on DuckDB version.
        try:
            con.execute("LOAD httpfs")
        except Exception as exc:
            con.close()
            raise RuntimeError("DuckDB could not load HTTP support.") from exc

    try:
        con.execute(
            "CREATE VIEW movie_view AS "
            "SELECT * FROM read_parquet(?)",
            [DATASET_URL],
        )
    except Exception as exc:
        con.close()
        raise RuntimeError(
            "Could not load the IMDb dataset. Check your internet connection "
            "and the dataset URL."
        ) from exc
    return con


def get_filters():
    return {
        "min_votes": str(st.session_state.get("min_votes", 1)),
        "min_rating": str(st.session_state.get("min_rating", 0.0)),
        "year": str(st.session_state.get("year", "")).strip(),
        "decade": st.session_state.get("decade", "Any"),
        "search": str(st.session_state.get("search", "")).strip(),
        "fuzzy": bool(st.session_state.get("fuzzy", False)),
        "runtime_min": str(st.session_state.get("runtime_min", 0)),
        "runtime_max": str(st.session_state.get("runtime_max", 3000)),
        "adult": bool(st.session_state.get("adult", True)),
        "excluded_genres": st.session_state.get("excluded_genres", []),
    }


def validate_filters(values):
    errors = []
    year = values["year"]
    if year:
        if not year.isdigit() or len(year) != 4:
            errors.append("Exact Year must be a four-digit year.")
        elif values["decade"] != "Any":
            decade = int(values["decade"])
            if not decade <= int(year) <= decade + 9:
                errors.append("Exact Year is outside the selected decade.")

    if int(values["runtime_min"] or 0) > int(values["runtime_max"] or 3000):
        errors.append("Minimum runtime cannot exceed maximum runtime.")

    return errors


with st.sidebar:
    st.header("🎛️ Curation Filters")

    st.number_input("Min Votes", value=1, step=10, min_value=0, key="min_votes")
    st.number_input(
        "Min Rating", value=0.0, step=0.1, min_value=0.0,
        max_value=10.0, key="min_rating"
    )

    c1, c2 = st.columns(2)
    c1.number_input("Min (m)", value=0, step=5, min_value=0, key="runtime_min")
    c2.number_input("Max (m)", value=3000, step=5, min_value=0, key="runtime_max")

    st.selectbox("Decade", DECADES, key="decade")
    st.text_input("Exact Year", key="year")
    st.text_input("Search Title", key="search")
    st.checkbox("Fuzzy Search", value=False, key="fuzzy")
    st.checkbox("Include Adult Titles", value=True, key="adult")

    st.multiselect(
        "Types", TITLE_TYPES, default=list(DEFAULT_TYPES), key="selected_types"
    )
    st.multiselect("✅ Include Genres", GENRES, key="selected_genres")
    st.multiselect("🚫 Exclude Genres", GENRES, key="excluded_genres")

    st.divider()

    if st.button("💾 Save Filters as Default", use_container_width=True):
        try:
            save_defaults({key: st.session_state.get(key) for key in DEFAULT_KEYS})
            st.success("Defaults saved.")
        except OSError as exc:
            st.error(f"Could not save defaults: {exc}")


st.title("🎲 IMDb Picker")
st.caption("Filter the IMDb dataset, then get a random selection from the matches.")

col1, col2 = st.columns(2)
with col1:
    sort_by = st.selectbox(
        "Sort generated picks by:",
        list(SORT_OPTIONS),
        key="sort_by",
        help=(
            "The picker first samples matching titles at random, then applies "
            "this ordering. It does not mean 'find the globally top-rated N'."
        ),
    )
with col2:
    num_picks = st.slider("How many picks?", 1, 100, 8, key="num_picks")

generate_btn = st.button(
    "🎲 Generate Picks", type="primary", use_container_width=True
)

if generate_btn:
    values = get_filters()
    errors = validate_filters(values)

    if errors:
        for error in errors:
            st.error(error)
        st.stop()

    genre_state = {genre: genre in st.session_state.get("selected_genres", [])
                   for genre in GENRES}
    type_state = {title_type: title_type in st.session_state.get("selected_types", [])
                  for title_type in TITLE_TYPES}

    where, params = build_where(values, genre_state, type_state)
    order_clause = SORT_OPTIONS[sort_by]

    try:
        with st.spinner("Querying database..."):
            con = get_connection()

            total = con.execute(
                f"SELECT COUNT(*) FROM movie_view WHERE {where}", params
            ).fetchone()[0]

            if total:
                base_select = """
                    SELECT
                        tconst,
                        primaryTitle,
                        COALESCE(NULLIF(startYear, '\\N'), 'N/A') AS startYear,
                        COALESCE(NULLIF(genres, '\\N'), 'No Genre') AS genres,
                        titleType,
                        NULLIF(runtimeMinutes, '\\N') AS runtimeMinutes,
                        averageRating,
                        numVotes
                    FROM movie_view
                    WHERE {where}
                """

                if sort_by == "Keep them Random":
                    sql = (
                        base_select.format(where=where)
                        + " ORDER BY random() LIMIT ?"
                    )
                    query_params = [*params, num_picks]
                else:
                    sql = f"""
                        WITH random_batch AS (
                            {base_select.format(where=where)}
                            ORDER BY random()
                            LIMIT ?
                        )
                        SELECT *
                        FROM random_batch
                        ORDER BY {order_clause}
                    """
                    query_params = [*params, num_picks]

                df = con.execute(sql, query_params).fetchdf()
            else:
                df = None

        if total == 0:
            st.warning("No matches found. Try adjusting your filters.")
        else:
            st.success(f"Found {total:,} total matches. Showing {len(df)} picks.")

            st.session_state["last_results"] = df.to_dict("records")
            st.session_state["last_total"] = total

    except Exception as exc:
        st.error(f"Database/query error: {exc}")


# Keep results visible across normal Streamlit reruns.
results = st.session_state.get("last_results", [])
if results:
    st.divider()
    st.subheader("Your Picks")

    for row in results:
        title = html.escape(str(row.get("primaryTitle", "Untitled")))
        yr = html.escape(str(row.get("startYear", "N/A")))
        genres = html.escape(str(row.get("genres", "No Genre")).replace(",", " • "))
        raw_type = str(row.get("titleType", "")).strip()
        t_type = html.escape(
            TYPE_MAP.get(raw_type, raw_type.title() if raw_type else "N/A")
        )
        runtime = format_runtime(row.get("runtimeMinutes"), as_hms=True) or "N/A"
        rating = format_rating(row.get("averageRating"))
        votes = format_votes(row.get("numVotes"))
        tconst = html.escape(str(row.get("tconst", "")))
        url = f"https://www.imdb.com/title/{tconst}/"

        st.markdown(
            f"""
            <div style="
                border: 1px solid rgba(128,128,128,.25);
                border-left: 4px solid #ff4b4b;
                border-radius: 8px;
                padding: 12px 14px;
                margin: 0 0 12px 0;
            ">
                <a href="{url}" target="_blank"
                   style="text-decoration:none;color:inherit;">
                    <h3 style="margin:0 0 7px 0;">{title}</h3>
                </a>
                <div style="opacity:.75;font-size:.9em;margin-bottom:7px;">
                    <strong>{yr}</strong> &bull; {t_type} &bull; {runtime}
                </div>
                <div style="opacity:.8;font-size:.9em;margin-bottom:7px;">
                    {genres}
                </div>
                <div>
                    ⭐ <strong>{rating}</strong>
                    <span style="opacity:.6;">({votes} votes)</span>
                    &nbsp;&nbsp;
                    <a href="{url}" target="_blank">IMDb ↗</a>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
