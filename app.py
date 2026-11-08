import hashlib
import html
import json
import os
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from filters import build_where
from queries import (
    RESULT_COLUMNS,
    SORT_OPTIONS,
    add_exclusions,
    build_selection_query,
    select_diverse_picks,
    sort_picks,
)
from watched import parse_watched_csv
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



DEFAULT_KEYS = [
    "min_votes", "min_rating", "runtime_min", "runtime_max",
    "decade", "year", "search", "fuzzy", "adult",
    "selected_types", "selected_genres", "excluded_genres", "genre_match",
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

for state_key, default in (
    ("imported_watched_ids", []),
    ("manual_watched_ids", []),
    ("saved_results", []),
    ("last_results", []),
):
    if state_key not in st.session_state:
        st.session_state[state_key] = default


@st.cache_resource(show_spinner=False)
def get_connection():
    con = duckdb.connect(":memory:")
    try:
        con.execute("INSTALL httpfs")
        con.execute("LOAD httpfs")
    except Exception:
        try:
            con.execute("LOAD httpfs")
        except Exception as exc:
            con.close()
            raise RuntimeError("DuckDB could not load HTTP support.") from exc

    try:
        safe_url = DATASET_URL.replace("'", "''")
        parquet_source = f"read_parquet('{safe_url}')"
        schema = con.execute(
            f"DESCRIBE SELECT * FROM {parquet_source}"
        ).fetchall()
        existing_columns = {row[0] for row in schema}

        # Keep older cached datasets usable until the next dataset refresh
        # publishes the optional original-title region/language columns.
        optional_columns = []
        for column in ("originalTitleRegion", "originalTitleLanguage"):
            if column not in existing_columns:
                optional_columns.append(f"NULL::VARCHAR AS {column}")

        additions = (
            ", " + ", ".join(optional_columns)
            if optional_columns else ""
        )
        con.execute(
            f"CREATE VIEW movie_view AS "
            f"SELECT *{additions} FROM {parquet_source}"
        )
    except Exception as exc:
        con.close()
        raise RuntimeError(f"Could not load the IMDb dataset: {exc}") from exc
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
        "genre_match": st.session_state.get("genre_match", "Any selected genre"),
    }


def get_genre_state():
    return {
        genre: genre in st.session_state.get("selected_genres", [])
        for genre in GENRES
    }


def get_type_state():
    return {
        title_type: title_type in st.session_state.get("selected_types", [])
        for title_type in TITLE_TYPES
    }


def current_watched_ids():
    return sorted(
        set(st.session_state.get("imported_watched_ids", []))
        | set(st.session_state.get("manual_watched_ids", []))
    )




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
    st.radio(
        "When multiple genres are selected",
        ["Any selected genre", "All selected genres"],
        key="genre_match",
        help="Any = OR; All = AND.",
    )
    st.multiselect("🚫 Exclude Genres", GENRES, key="excluded_genres")

    st.divider()
    st.subheader("Watched titles")
    watched_file = st.file_uploader(
        "Import IMDb watched-list CSV",
        type=["csv"],
        help="Use an IMDb list export containing the Const column. Only IMDb IDs are imported.",
    )

    if watched_file is None:
        if st.session_state.get("watched_upload_signature") is not None:
            st.session_state["watched_upload_signature"] = None
            st.session_state["imported_watched_ids"] = []
    else:
        uploaded_bytes = watched_file.getvalue()
        signature = hashlib.sha256(uploaded_bytes).hexdigest()
        if signature != st.session_state.get("watched_upload_signature"):
            try:
                imported_ids = parse_watched_csv(uploaded_bytes)
                st.session_state["imported_watched_ids"] = imported_ids
                st.session_state["watched_upload_signature"] = signature
                st.success(f"Imported {len(imported_ids):,} watched titles.")
            except Exception as exc:
                st.error(f"Could not read watched-list CSV: {exc}")

    watched_ids = current_watched_ids()
    if watched_ids:
        st.caption(f"{len(watched_ids):,} watched titles will be excluded.")
        watched_csv = pd.DataFrame({"Const": watched_ids}).to_csv(index=False)
        st.download_button(
            "Download watched IDs",
            watched_csv,
            file_name="imdb-watched-ids.csv",
            mime="text/csv",
            use_container_width=True,
        )

    st.divider()
    if st.button("💾 Save Filters as Default", use_container_width=True):
        try:
            save_defaults({key: st.session_state.get(key) for key in DEFAULT_KEYS})
            st.success("Defaults saved.")
        except OSError as exc:
            st.error(f"Could not save defaults: {exc}")
    st.caption("Saved defaults are stored on the app server, not in a personal account.")


st.title("🎲 IMDb Picker")
st.caption("Filter the IMDb dataset, then get a random selection from the matches.")

generation_mode = st.radio(
    "How should picks be selected?",
    ["Standard Random", "Discovery"],
    horizontal=True,
    key="generation_mode",
    help=(
        "Discovery samples evenly across four popularity quartiles, from less "
        "widely rated titles to the most popular. Your filters still apply."
    ),
)
discovery_strength = 80
if generation_mode == "Discovery":
    st.caption(
        "Discovery balances popularity, rating, decade, genre and—when available—"
        "original-title region and language. It samples a bounded random candidate "
        "pool, then chooses titles that fill underrepresented categories."
    )
    discovery_strength = st.slider(
        "Diversity strength",
        min_value=0,
        max_value=100,
        value=80,
        step=5,
        help=(
            "0 = random selection from the candidate pool. 100 = strongly favors "
            "categories not yet represented in this batch."
        ),
    )

col1, col2 = st.columns(2)
with col1:
    sort_by = st.selectbox(
        "Sort generated picks by:",
        list(SORT_OPTIONS),
        key="sort_by",
        help=(
            "The picker samples titles first, then applies this ordering. "
            "It does not find the globally top-rated N unless you use a separate "
            "whole-pool ranking workflow."
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

    genre_state = get_genre_state()
    type_state = get_type_state()
    where, params = build_where(values, genre_state, type_state)
    where, query_params = add_exclusions(
        where, params, watched_ids=current_watched_ids()
    )

    try:
        with st.spinner("Querying database..."):
            con = get_connection()
            total = con.execute(
                f"SELECT COUNT(*) FROM movie_view WHERE {where}", query_params
            ).fetchone()[0]

            if total:
                sql = build_selection_query(
                    where, sort_by, num_picks, generation_mode
                )
                if generation_mode == "Discovery":
                    candidate_limit = min(20000, max(4000, num_picks * 150))
                    candidate_df = con.execute(
                        sql, [*query_params, candidate_limit]
                    ).fetchdf()
                    selected = select_diverse_picks(
                        candidate_df.to_dict("records"),
                        num_picks,
                        diversity_strength,
                    )
                    selected = sort_picks(selected, sort_by)
                    df = pd.DataFrame(selected)
                else:
                    df = con.execute(
                        sql, [*query_params, num_picks]
                    ).fetchdf()
            else:
                df = None

        if total == 0:
            st.session_state["last_results"] = []
            st.session_state["last_total"] = 0
            st.warning("No matches found. Try adjusting your filters or watched list.")
        else:
            st.success(
                f"Found {total:,} eligible titles. Showing {len(df)} picks."
            )
            st.session_state["last_results"] = df.to_dict("records")
            st.session_state["last_total"] = total
            st.session_state["last_context"] = {
                "values": values,
                "genres": genre_state,
                "types": type_state,
            }

    except Exception as exc:
        st.error(f"Database/query error: {exc}")


# Replacements are processed before cards are drawn, so only the changed card
# is refreshed and the rest of the current batch remains untouched.
replace_index = st.session_state.pop("replace_requested", None)
if isinstance(replace_index, int):
    results = st.session_state.get("last_results", [])
    context = st.session_state.get("last_context")
    if context and 0 <= replace_index < len(results):
        try:
            where, params = build_where(
                context["values"], context["genres"], context["types"]
            )
            current_ids = [str(row.get("tconst", "")) for row in results]
            where, query_params = add_exclusions(
                where,
                params,
                watched_ids=current_watched_ids(),
                excluded_ids=current_ids,
            )
            con = get_connection()
            replacement_df = con.execute(
                f"""
                SELECT {RESULT_COLUMNS}
                FROM movie_view
                WHERE {where}
                ORDER BY random()
                LIMIT 1
                """,
                query_params,
            ).fetchdf()

            if replacement_df.empty:
                st.warning("No unused titles remain for this filter combination.")
            else:
                results[replace_index] = replacement_df.iloc[0].to_dict()
                st.session_state["last_results"] = results
                st.toast("Pick replaced.")
        except Exception as exc:
            st.error(f"Could not replace this pick: {exc}")


results = st.session_state.get("last_results", [])
if results:
    st.divider()
    st.subheader("Your Picks")

    picks_csv = pd.DataFrame(results).to_csv(index=False)
    st.download_button(
        "Download current picks",
        picks_csv,
        file_name="imdb-picks.csv",
        mime="text/csv",
    )

    for index, row in enumerate(results):
        title = html.escape(str(row.get("primaryTitle", "Untitled")))
        year = html.escape(str(row.get("startYear", "N/A")))
        genres = html.escape(
            str(row.get("genres", "No Genre")).replace(",", " • ")
        )
        raw_type = str(row.get("titleType", "")).strip()
        title_type = html.escape(
            TYPE_MAP.get(raw_type, raw_type.title() if raw_type else "N/A")
        )
        runtime = format_runtime(row.get("runtimeMinutes"), as_hms=True) or "N/A"
        rating = format_rating(row.get("averageRating"))
        votes = format_votes(row.get("numVotes"))
        tconst = str(row.get("tconst", ""))
        safe_tconst = html.escape(tconst)
        url = f"https://www.imdb.com/title/{safe_tconst}/"

        card_col, action_col = st.columns([5, 1])
        with card_col:
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
                        <strong>{year}</strong> &bull; {title_type} &bull; {runtime}
                    </div>
                    <div style="opacity:.8;font-size:.9em;margin-bottom:7px;">
                        {genres}
                    </div>
                    <div style="opacity:.7;font-size:.85em;margin-bottom:7px;">
                        Original-title region: {html.escape(str(row.get("originalTitleRegion") or "Unknown"))}
                        &nbsp; · &nbsp;
                        Original-title language: {html.escape(str(row.get("originalTitleLanguage") or "Unknown"))}
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

        with action_col:
            if st.button("↻ Replace", key=f"replace_{index}", use_container_width=True):
                st.session_state["replace_requested"] = index
                st.rerun()

            if st.button("☆ Keep", key=f"keep_{index}", use_container_width=True):
                saved = st.session_state.get("saved_results", [])
                if not any(item.get("tconst") == tconst for item in saved):
                    saved.append(dict(row))
                    st.session_state["saved_results"] = saved
                    st.toast("Added to your shortlist.")

            if st.button("✓ Watched", key=f"watched_{index}", use_container_width=True):
                manual_ids = set(st.session_state.get("manual_watched_ids", []))
                manual_ids.add(tconst)
                st.session_state["manual_watched_ids"] = sorted(manual_ids)
                current_results = st.session_state.get("last_results", [])
                current_results.pop(index)
                st.session_state["last_results"] = current_results
                st.rerun()

saved_results = st.session_state.get("saved_results", [])
if saved_results:
    st.divider()
    st.subheader(f"Shortlist ({len(saved_results)})")
    shortlist_csv = pd.DataFrame(saved_results).to_csv(index=False)
    st.download_button(
        "Download shortlist",
        shortlist_csv,
        file_name="imdb-shortlist.csv",
        mime="text/csv",
    )
