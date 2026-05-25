import streamlit as st
import duckdb
import pandas as pd
import urllib.request
import json
from filters import build_where
from utils import (
    GENRES, TITLE_TYPES, DEFAULT_TYPES, DECADES, TYPE_MAP,
    format_runtime, format_votes, format_rating
)

# --- PASTE YOUR GOOGLE APPS SCRIPT WEBHOOK URL HERE ---
SHEETS_WEBHOOK_URL = "PASTE_YOUR_WEBHOOK_URL_HERE"

# --- PAGE CONFIG ---
st.set_page_config(page_title="IMDb Picker", page_icon="🎬", layout="centered", initial_sidebar_state="collapsed")

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

# --- GOOGLE SHEETS HELPER ---
def log_to_sheets(tab_name, row_data):
    payload = json.dumps({"row": row_data}).encode('utf-8')
    req = urllib.request.Request(
        f"{SHEETS_WEBHOOK_URL}?tab={tab_name}", 
        data=payload, 
        headers={'Content-Type': 'application/json'}
    )
    try:
        urllib.request.urlopen(req, timeout=5)
        return True
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return False

# --- MAIN AREA ---
st.title("🎲 IMDb Picker")

# MOBILE-FRIENDLY FILTERS (Main Page Expander instead of Sidebar)
with st.expander("🎛️ Curation Filters", expanded=True):
    c1, c2 = st.columns(2)
    min_votes = c1.number_input("Min Votes", value=50, step=10, min_value=0)
    min_rating = c2.number_input("Min Rating", value=0.0, step=0.1, min_value=0.0, max_value=10.0)
    
    c3, c4 = st.columns(2)
    runtime_min = c3.number_input("Runtime Min (m)", value=0, step=5, min_value=0)
    runtime_max = c4.number_input("Runtime Max (m)", value=300, step=5, min_value=0)

    decade = st.selectbox("Decade", DECADES)
    year = st.text_input("Exact Year")
    
    sc1, sc2 = st.columns([2, 1])
    search = sc1.text_input("Search Title")
    fuzzy = sc2.checkbox("Fuzzy Search", value=False)

    adult = st.checkbox("Include Adult Titles", value=False)
    selected_types = st.multiselect("Types", TITLE_TYPES, default=list(DEFAULT_TYPES))
    selected_genres = st.multiselect("Genres", GENRES)

# ACTION BAR
ac1, ac2 = st.columns([1, 2])
num_picks = ac1.slider("Picks", 1, 100, 8)

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
sort_by = ac2.selectbox("Sort generated picks by:", list(SORT_OPTIONS.keys()))

generate_btn = st.button("🎲 Generate Picks", type="primary", use_container_width=True)

# --- QUERY LOGIC ---
if generate_btn:
    values = {
        'min_votes': str(min_votes) if min_votes > 0 else "",
        'min_rating': str(min_rating) if min_rating > 0.0 else "",
        'year': str(year).strip(), 'decade': decade, 'search': search.strip(),
        'fuzzy': fuzzy, 'runtime_min': str(runtime_min) if runtime_min > 0 else "",
        'runtime_max': str(runtime_max) if runtime_max > 0 else "", 'adult': adult
    }
    
    genre_state = {g: (g in selected_genres) for g in GENRES}
    type_state = {t: (t in selected_types) for t in TITLE_TYPES}
    where, params = build_where(values, genre_state, type_state)
    order_clause = SORT_OPTIONS[sort_by]
    
    with st.spinner("Querying database..."):
        con = get_connection()
        total = con.execute(f"SELECT COUNT(*) FROM movie_view WHERE {where}", params).fetchone()[0]
        if total == 0:
            st.warning("No matches found.")
            st.stop()
            
        # HANDLE \N AT THE DATABASE LEVEL
        # NULLIF converts '\N' strings to actual SQL NULLs
        # COALESCE provides clean fallback values for display
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
    
    # --- RESULTS & DYNAMIC LOGGING UI ---
    for _, row in df.iterrows():
        title = str(row['primaryTitle'])
        yr = str(row['startYear'])  # Already cleaned by SQL!
        genres = str(row['genres']).replace(',', ' • ')  # Already cleaned by SQL!
        
        rt = format_runtime(row['runtimeMinutes'], as_hms=True)
        if not rt: rt = 'N/A'
        
        raw_type = str(row.get('titleType', '')).strip()
        t_type = TYPE_MAP.get(raw_type, raw_type.title() if raw_type else 'N/A')
        
        rating = format_rating(row['averageRating'])
        votes = format_votes(row['numVotes'])
        url = f"https://www.imdb.com/title/{row['tconst']}/"
        
        # Movie Card
        st.markdown(f"""
        <div style="border-left: 4px solid #ff4b4b; padding: 5px 0 5px 15px; margin-bottom: 5px;">
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
        
        # Dynamic Logging Expander
        with st.expander(f"Log '{title}'"):
            tab_choice = st.selectbox(
                "Add to tab:", 
                ["movies", "tv shows", "completed tv shows"], 
                key=f"tab_{row['tconst']}"
            )
            
            row_data = []
            if tab_choice == "movies":
                summary = st.text_input("Plot Summary (1 sentence)", key=f"sum_{row['tconst']}")
                my_rating = st.slider("My Rating (1-10)", 1, 10, 5, key=f"rat_{row['tconst']}")
                liked = st.text_area("What I liked", height=68, key=f"lik_{row['tconst']}")
                row_data = [title, summary, my_rating, liked]
                
            elif tab_choice == "tv shows":
                season = st.number_input("Current Season", 1, 100, 1, key=f"sea_{row['tconst']}")
                episode = st.number_input("Next Episode", 1, 100, 1, key=f"ep_{row['tconst']}")
                row_data = [title, season, episode]
                
            elif tab_choice == "completed tv shows":
                st.info("Will log as: **Name** | complete | complete")
                row_data = [title, "complete", "complete"]

            if st.button("✅ Log it!", key=f"log_{row['tconst']}", use_container_width=True):
                with st.spinner("Sending to Sheets..."):
                    if log_to_sheets(tab_choice, row_data):
                        st.success(f"Logged to '{tab_choice}'!")
                    else:
                        st.error("Failed. Check URL.")
        
        st.markdown("---")
