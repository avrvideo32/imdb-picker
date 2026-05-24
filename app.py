import streamlit as st
import duckdb
import pandas as pd
from filters import build_where
from utils import (
    GENRES, TITLE_TYPES, DEFAULT_TYPES, DECADES,
    format_runtime, format_votes, format_rating
)

# --- PAGE CONFIG ---
st.set_page_config(page_title="IMDb Picker", page_icon="🎬", layout="centered", initial_sidebar_state="expanded")

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_connection():
    con = duckdb.connect(':memory:')
    parquet_url = "https://huggingface.co/datasets/Avrozavr/Imdb/resolve/main/imdb_cache.parquet"
    try:
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")
    except Exception:
        pass
    con.execute(f"CREATE VIEW movie_view AS SELECT * FROM read_parquet('{parquet_url}')")
    return con

# --- SIDEBAR (Filters) ---
st.sidebar.title("🎬 Filters")

with st.sidebar.expander("Core Metrics", expanded=True):
    min_votes = st.number_input("Min Votes", value=50, step=10, min_value=0)
    min_rating = st.number_input("Min Rating", value=0.0, step=0.1, min_value=0.0, max_value=10.0)
    
    c1, c2 = st.columns(2)
    runtime_min = c1.number_input("Min (m)", value=0, step=5, min_value=0)
    runtime_max = c2.number_input("Max (m)", value=300, step=5, min_value=0)

with st.sidebar.expander("Year & Search"):
    decade = st.selectbox("Decade", DECADES)
    year = st.text_input("Exact Year")
    search = st.text_input("Search Title")
    fuzzy = st.checkbox("Fuzzy Search", value=False)

with st.sidebar.expander("Categories"):
    adult = st.checkbox("Include Adult", value=False)
    selected_types = st.multiselect("Types", TITLE_TYPES, default=list(DEFAULT_TYPES))
    selected_genres = st.multiselect("Genres", GENRES)

# --- MAIN AREA ---
st.title("🎲 IMDb Picker")

num_picks = st.slider("How many random picks?", 1, 100, 8)

# Sorting options for the FINAL batch of picks
SORT_OPTIONS = {
    "Keep them Random": "random()",
    "Rating (High to Low)": "averageRating DESC NULLS LAST",
    "Rating (Low to High)": "averageRating ASC NULLS LAST",
    "Year (Newest)": "TRY_CAST(startYear AS INT) DESC NULLS LAST",
    "Year (Oldest)": "TRY_CAST(startYear AS INT) ASC NULLS LAST",
    "Votes (Most Popular)": "numVotes DESC NULLS LAST",
    "Runtime (Longest)": "TRY_CAST(runtimeMinutes AS INT) DESC NULLS LAST",
    "Runtime (Shortest)": "TRY_CAST(runtimeMinutes AS INT) ASC NULLS LAST",
    "Title (A-Z)": "primaryTitle ASC NULLS LAST"
}

sort_by = st.selectbox("Sort the generated picks by:", list(SORT_OPTIONS.keys()))

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
        'runtime_max': str(runtime_max) if runtime_max > 0 else "",
        'adult': adult
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
            st.stop()
            
        # THE MAGIC: 
        # If random, just grab them. 
        # If sorting, use a CTE to grab the random batch FIRST, then sort that specific batch.
        if sort_by == "Keep them Random":
            sql = f"SELECT * FROM movie_view WHERE {where} ORDER BY random() LIMIT {num_picks}"
        else:
            sql = f"""
                WITH random_batch AS (
                    SELECT * FROM movie_view WHERE {where} ORDER BY random() LIMIT {num_picks}
                )
                SELECT * FROM random_batch ORDER BY {order_clause}
            """
            
        df = con.execute(sql, params).fetchdf()
        
    st.success(f"Found {total:,} total matches! Here are your {len(df)} random picks, sorted by **{sort_by}**.")
    
    # --- MOBILE-OPTIMIZED RESULTS (Card Layout) ---
    html_cards = ""
    for _, row in df.iterrows():
        title = str(row['primaryTitle'])
        yr = str(row['startYear']).replace('\\N', 'N/A')
        
        rt_raw = row['runtimeMinutes']
        rt = format_runtime(rt_raw, as_hms=True)
        if rt == '\\N' or not rt: rt = 'N/A'
        
        genres = str(row['genres']).replace('\\N', 'No Genre').replace(',', ' • ')
        rating = format_rating(row['averageRating'])
        votes = format_votes(row['numVotes'])
        url = f"https://www.imdb.com/title/{row['tconst']}/"
        
        html_cards += f"""
        <div style="border-left: 4px solid #ff4b4b; padding: 5px 0 5px 15px; margin-bottom: 20px;">
            <a href="{url}" target="_blank" style="text-decoration: none; color: inherit;">
                <h3 style="margin: 0 0 5px 0;">{title}</h3>
            </a>
            <p style="margin: 0 0 5px 0; font-size: 0.9em; opacity: 0.8;">
                <strong>{yr}</strong> &bull; {rt} &bull; {genres}
            </p>
            <p style="margin: 0; font-size: 1em;">
                ⭐ <strong>{rating}</strong> <span style="opacity: 0.6;">({votes} votes)</span>
            </p>
        </div>
        """
        
    st.markdown(html_cards, unsafe_allow_html=True)
