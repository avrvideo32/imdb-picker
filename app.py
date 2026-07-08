import streamlit as st
import duckdb
import html
import json
import os
from filters import build_where
from utils import (
    GENRES, TITLE_TYPES, DEFAULT_TYPES, DECADES, TYPE_MAP,
    format_runtime, format_votes, format_rating
)

# --- DEFAULTS MANAGEMENT ---
DEFAULTS_FILE = "user_defaults.json"

def load_defaults():
    if os.path.exists(DEFAULTS_FILE):
        try:
            with open(DEFAULTS_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_defaults(data):
    with open(DEFAULTS_FILE, "w") as f:
        json.dump(data, f)

# Load saved defaults into session state on first run
if "initialized" not in st.session_state:
    saved_defaults = load_defaults()
    for key, value in saved_defaults.items():
        st.session_state[key] = value
    st.session_state.initialized = True

# --- PAGE CONFIG ---
st.set_page_config(page_title="IMDb Picker", page_icon="🎬", layout="centered")

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_connection():
    con = duckdb.connect(':memory:')
    # 👇 UPDATE THIS TO YOUR NEW HUGGING FACE DATASET URL
    parquet_url = "https://huggingface.co/datasets/Avrozavr/Imdb/resolve/main/imdb_cache.parquet"
    try:
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")
    except Exception:
        pass
    con.execute(f"CREATE VIEW movie_view AS SELECT * FROM read_parquet('{parquet_url}')")
    return con

# --- SIDEBAR (Filters Only) ---
with st.sidebar:
    st.header("🎛️ Curation Filters")
    
    # By assigning a `key` to each widget, Streamlit automatically binds it to st.session_state.
    # If we loaded defaults into st.session_state earlier, the widgets will automatically show those saved values!
    min_votes = st.number_input("Min Votes", value=0, step=10, min_value=1, key="min_votes")
    min_rating = st.number_input("Min Rating", value=0.0, step=0.1, min_value=0.0, max_value=10.0, key="min_rating")
    
    c1, c2 = st.columns(2)
    runtime_min = c1.number_input("Min (m)", value=0, step=5, min_value=0, key="runtime_min")
    runtime_max = c2.number_input("Max (m)", value=3000, step=5, min_value=0, key="runtime_max")
    
    decade = st.selectbox("Decade", DECADES, key="decade")
    year = st.text_input("Exact Year", key="year")
    search = st.text_input("Search Title", key="search")
    fuzzy = st.checkbox("Fuzzy Search", value=False, key="fuzzy")
    adult = st.checkbox("Include Adult Titles", value=True, key="adult")
    
    selected_types = st.multiselect("Types", TITLE_TYPES, default=list(DEFAULT_TYPES), key="selected_types")
    selected_genres = st.multiselect("✅ Include Genres", GENRES, key="selected_genres")
    excluded_genres = st.multiselect("🚫 Exclude Genres", GENRES, key="excluded_genres")
    
    st.divider()
    
    # SAVE DEFAULTS BUTTON
    if st.button("💾 Save Filters as Default", use_container_width=True):
        # Grab all current widget values from session state
        keys_to_save = [
            'min_votes', 'min_rating', 'runtime_min', 'runtime_max', 
            'decade', 'year', 'search', 'fuzzy', 'adult', 
            'selected_types', 'selected_genres', 'excluded_genres'
        ]
        current_settings = {k: st.session_state.get(k) for k in keys_to_save}
        save_defaults(current_settings)
        st.success("Defaults saved!")

# --- MAIN SCREEN ---
st.title("🎲 IMDb Picker")

# Execution Controls
col1, col2 = st.columns([1, 1])
with col1:
    SORT_OPTIONS = {
        "Votes (Most Popular)": "TRY_CAST(numVotes AS INT) DESC NULLS LAST",
        "Keep them Random": "random()",
        "Rating (High to Low)": "TRY_CAST(averageRating AS DOUBLE) DESC NULLS LAST",
        "Rating (Low to High)": "TRY_CAST(averageRating AS DOUBLE) ASC NULLS LAST",
        "Year (Newest)": "TRY_CAST(startYear AS INT) DESC NULLS LAST",
        "Year (Oldest)": "TRY_CAST(startYear AS INT) ASC NULLS LAST",
        "Runtime (Longest)": "TRY_CAST(runtimeMinutes AS INT) DESC NULLS LAST",
        "Runtime (Shortest)": "TRY_CAST(runtimeMinutes AS INT) ASC NULLS LAST",
        "Title (A-Z)": "primaryTitle ASC NULLS LAST"
    }
    sort_by = st.selectbox("Sort generated picks by:", list(SORT_OPTIONS.keys()), key="sort_by")

with col2:
    num_picks = st.slider("How many picks?", 1, 100, 8, key="num_picks")

generate_btn = st.button("🎲 Generate Picks", type="primary", use_container_width=True)

# --- QUERY LOGIC ---
if generate_btn:
    values = {
        'min_votes': str(min_votes) if min_votes > 0 else "",
        'min_rating': str(min_rating) if min_rating > 0.0 else "",
        'year': str(year).strip(),
        'decade': decade,
        'search': search.strip(),
        'fuzzy': fuzzy,
        'runtime_min': str(runtime_min) if runtime_min > 0 else "",
        'runtime_max': str(runtime_max) if runtime_max < 3000 else "",
        'adult': adult,
        'excluded_genres': excluded_genres
    }
    
    genre_state = {g: (g in selected_genres) for g in GENRES}
    type_state = {t: (t in selected_types) for t in TITLE_TYPES}
    
    where, params = build_where(values, genre_state, type_state)
    order_clause = SORT_OPTIONS[sort_by]
    
    with st.spinner("Querying database..."):
        con = get_connection()
        total = con.execute(f"SELECT COUNT(*) FROM movie_view WHERE {where}", params).fetchone()[0]
        
        if total == 0:
            st.warning("No matches found. Try adjusting your filters.")
        else:
            base_select = """
                SELECT
                    tconst, primaryTitle,
                    COALESCE(NULLIF(startYear, '\\N'), 'N/A') as startYear,
                    COALESCE(NULLIF(genres, '\\N'), 'No Genre') as genres,
                    titleType,
                    NULLIF(runtimeMinutes, '\\N') as runtimeMinutes,
                    averageRating, numVotes
            """
            
            if sort_by == "Keep them Random":
                sql = f"{base_select} FROM movie_view WHERE {where} ORDER BY random() LIMIT {num_picks}"
            else:
                sql = f"""
                    WITH random_batch AS ({base_select} FROM movie_view WHERE {where} ORDER BY random() LIMIT {num_picks})
                    SELECT * FROM random_batch ORDER BY {order_clause}
                """
            
            df = con.execute(sql, params).fetchdf()
            
            st.success(f"Found {total:,} total matches! Showing {len(df)} picks.")
            
            # --- RESULTS UI ---
            for _, row in df.iterrows():
                title = html.escape(str(row['primaryTitle']))
                yr = html.escape(str(row['startYear']))
                genres = html.escape(str(row['genres']).replace(',', ' • '))
                rt = format_runtime(row['runtimeMinutes'], as_hms=True) or 'N/A'
                
                raw_type = str(row.get('titleType', '')).strip()
                t_type = html.escape(TYPE_MAP.get(raw_type, raw_type.title() if raw_type else 'N/A'))
                
                rating = format_rating(row['averageRating'])
                votes = format_votes(row['numVotes'])
                url = f"https://www.imdb.com/title/{row['tconst']}/"
                
                st.markdown(f"""
                <div style="border-left: 4px solid #ff4b4b; padding: 5px 0 5px 15px; margin-bottom: 15px;">
                    <a href="{url}" target="_blank" style="text-decoration: none; color: inherit;">
                        <h3 style="margin: 0 0 5px 0;">{title}</h3>
                    </a>
                    <p style="margin: 0 0 5px 0; font-size: 0.9em; opacity: 0.8;">
                        <strong>{yr}</strong> &bull; {t_type} &bull; {rt} &bull; {genres}
                    </p>
                    <p style="margin: 0; font-size: 1em;">
                        ⭐ <strong>{rating}</strong> <span style="opacity: 0.6;">({votes} votes)</span>
                    </p>
                </div>
                """, unsafe_allow_html=True)
