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

# --- PAGE CONFIG & SIDEBAR REMOVAL ---
st.set_page_config(page_title="IMDb Picker", page_icon="🎬", layout="centered", initial_sidebar_state="auto")

# Force-hide the empty sidebar completely via CSS
st.markdown("""
<style>
    /* Hide the sidebar container entirely */
    section[data-testid="stSidebar"] {
        display: none !important;
    }
    /* Remove the extra padding Streamlit adds when a sidebar exists */
    .main .block-container {
        padding-left: 1rem !important;
        padding-right: 1rem !important;
        max-width: 100% !important;
    }
</style>
""", unsafe_allow_html=True)

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

# --- MAIN AREA ---
st.title("🎲 IMDb Picker")
