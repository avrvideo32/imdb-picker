import streamlit as st
import duckdb
import html
from filters import build_where
from utils import (
    GENRES, TITLE_TYPES, DEFAULT_TYPES, DECADES, TYPE_MAP,
    format_runtime, format_votes, format_rating
)

# --- PAGE CONFIG ---
st.set_page_config(page_title="IMDb Picker", page_icon="🎬", layout="centered")

# --- DATABASE CONNECTION ---
@st.cache_resource
def get_connection():
    con = duckdb.connect(':memory:')
    
    # 👇 UPDATE THIS TO YOUR NEW HUGGING FACE DATASET URL
    parquet_url = "https://huggingface.co/datasets/Avrozavr/Imdb/imdb_cache.parquet"
    
    try:
        con.execute("INSTALL httpfs;")
        con.execute("LOAD httpfs;")
    except Exception:
        pass
    con.execute(f"CREATE VIEW movie_view AS SELECT * FROM read_parquet('{parquet_url}')")
    return con

# --- MAIN AREA ---
st.title("🎲 IMDb Picker")

# --- SIDEBAR (Filters & Form) ---
with st.sidebar:
    with st.form("filter_form"):
        st.header("🎛️ Curation Filters")
        
        min_votes = st.number_input("Min Votes", value=0, step=10, min_value=0)
        min_rating = st.number_input("Min Rating", value=0.0, step=0.1, min_value=0.0, max_value=10.0)
        
        c1, c2 = st.columns(2)
        runtime_min = c1.number_input("Min (m)", value=0, step=5, min_value=0)
        runtime_max = c2.number_input("Max (m)", value=3000, step=5, min_value=0)
        
        decade = st.selectbox("Decade", DECADES)
        year = st.text_input("Exact Year")
        search = st.text_input("Search Title")
        fuzzy = st.checkbox("Fuzzy Search", value=False)
        adult = st.checkbox("Include Adult Titles", value=True)
        
        selected_types = st.multiselect("Types", TITLE_TYPES, default=list(DEFAULT_TYPES))
        selected_genres = st.multiselect("✅ Include Genres", GENRES)
        excluded_genres = st.multiselect("🚫 Exclude Genres", GENRES)
        
        # NO TRAILING SPACES! Added TRY_CAST to Votes and Rating for safe sorting
        SORT_OPTIONS = {
            "Votes (Most Popular)": "TRY_CAST(numVotes AS INT) DESC NULLS LAST",
            "Rating (High to Low)": "TRY_CAST(averageRating AS DOUBLE) DESC NULLS LAST",
            "Keep them Random": "random()",
            "Rating (Low to High)": "TRY_CAST(averageRating AS DOUBLE) ASC NULLS LAST",
            "Year (Newest)": "TRY_CAST(startYear AS INT) DESC NULLS LAST",
            "Year (Oldest)": "TRY_CAST(startYear AS INT) ASC NULLS LAST",
            "Runtime (Longest)": "TRY_CAST(runtimeMinutes AS INT) DESC NULLS LAST",
            "Runtime (Shortest)": "TRY_CAST(runtimeMinutes AS INT) ASC NULLS LAST",
            "Title (A-Z)": "primaryTitle ASC NULLS LAST"
        }
        
        sort_by = st.selectbox("Sort generated picks by:", list(SORT_OPTIONS.keys()))
        num_picks = st.slider("How many picks?", 1, 100, 8)
        
        generate_btn = st.form_submit_button("🎲 Generate Picks", type="primary", use_container_width=True)

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
                # html.escape prevents XSS vulnerabilities
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
else:
    st.info("👈 Adjust the filters in the sidebar and click **Generate Picks** to find your next watch!")
