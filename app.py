import streamlit as st
import duckdb
import pandas as pd
from pathlib import Path
from filters import build_where
from utils import (
    GENRES, TITLE_TYPES, DEFAULT_TYPES, DECADES,
    format_runtime, format_votes, format_rating
)

# --- PAGE CONFIG ---
st.set_page_config(page_title="IMDb Picker", page_icon="🎬", layout="wide", initial_sidebar_state="expanded")


# --- DATABASE CONNECTION ---
@st.cache_resource
def get_connection():
    con = duckdb.connect(':memory:')
    
    # Your Hugging Face URL
    parquet_url = "https://huggingface.co/datasets/Avrozavr/Imdb/resolve/main/imdb_cache.parquet"
    
    # Install and load the extension that allows DuckDB to read files over HTTPS
    try:
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")
    except Exception:
        pass  # It might already be loaded in newer DuckDB versions
        
    # Create the view directly from the URL (No local Path check needed!)
    con.execute(f"CREATE VIEW movie_view AS SELECT * FROM read_parquet('{parquet_url}')")
    
    return con


# --- SIDEBAR (Filters) ---
st.sidebar.title("🎬 Curation Filters")

with st.sidebar.expander("Core Metrics", expanded=True):
    # We use strings for numbers to perfectly match your existing filters.py logic
    min_votes = st.number_input("Min Votes", value=50, step=10, min_value=0)
    min_rating = st.number_input("Min Rating", value=0.0, step=0.1, min_value=0.0, max_value=10.0)

    c1, c2 = st.columns(2)
    runtime_min = c1.number_input("Runtime Min", value=0, step=5, min_value=0)
    runtime_max = c2.number_input("Runtime Max", value=300, step=5, min_value=0)

with st.sidebar.expander("Year & Search"):
    decade = st.selectbox("Decade", DECADES)
    year = st.text_input("Exact Year")
    search = st.text_input("Search Title")
    fuzzy = st.checkbox("Fuzzy Search (Slower)", value=False)

with st.sidebar.expander("Categories & Types"):
    adult = st.checkbox("Include Adult Titles", value=False)

    # Multiselect is MUCH better for mobile than 30 checkboxes
    selected_types = st.multiselect("Title Types", TITLE_TYPES, default=list(DEFAULT_TYPES))
    selected_genres = st.multiselect("Genres", GENRES)

# --- MAIN AREA ---
st.title("🎲 IMDb Random Picker")

col1, col2 = st.columns([1, 3])
with col1:
    num_picks = st.slider("Picks", 1, 50, 8)
with col2:
    st.write("")  # Spacer
    st.write("")  # Spacer
    generate_btn = st.button("🎲 Generate Picks", type="primary", use_container_width=True)

# --- QUERY LOGIC ---
if generate_btn:
    # 1. Format values to match your existing Tkinter StringVar behavior
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

    # 2. Build Query
    where, params = build_where(values, genre_state, type_state)

    # 3. Execute Query
    with st.spinner("Querying database..."):
        con = get_connection()
        total = con.execute(f"SELECT COUNT(*) FROM movie_view WHERE {where}", params).fetchone()[0]

        if total == 0:
            st.warning("No matches found. Try adjusting your filters.")
            st.stop()

        sql = f"SELECT * FROM movie_view WHERE {where} ORDER BY random() LIMIT {num_picks}"
        df = con.execute(sql, params).fetchdf()

    # 4. Format and Display Results
    st.success(f"Found {total:,} matches. Here are your {len(df)} picks:")

    # Format columns for nice mobile viewing
    df['Rating'] = df['averageRating'].apply(format_rating)
    df['Votes'] = df['numVotes'].apply(format_votes)
    df['Runtime'] = df['runtimeMinutes'].apply(lambda x: format_runtime(x, as_hms=True))
    df['IMDb Link'] = df['tconst'].apply(lambda x: f"https://www.imdb.com/title/{x}/")

    # Rename and select columns for the final table
    display_df = df[['primaryTitle', 'startYear', 'genres', 'Runtime', 'Rating', 'Votes', 'IMDb Link']].copy()
    display_df.rename(columns={
        'primaryTitle': 'Title',
        'startYear': 'Year',
        'genres': 'Genres'
    }, inplace=True)

    st.dataframe(
        display_df,
        column_config={
            "IMDb Link": st.column_config.LinkColumn("Link", display_text="🔗 Open IMDb"),
            "Title": st.column_config.TextColumn("Title", width="large"),
            "Genres": st.column_config.TextColumn("Genres", width="medium")
        },
        hide_index=True,
        use_container_width=True
    )
