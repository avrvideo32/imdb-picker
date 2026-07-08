import os
import sys
import requests
import duckdb
from huggingface_hub import HfApi, login

def main():
    # 1. Define URLs and file paths
    basics_url = "https://datasets.imdbws.com/title.basics.tsv.gz"
    ratings_url = "https://datasets.imdbws.com/title.ratings.tsv.gz"
    
    basics_file = "title.basics.tsv.gz"
    ratings_file = "title.ratings.tsv.gz"
    parquet_file = "imdb_cache.parquet"
    
    # 2. Download files (requests is still the easiest way to download the raw .gz files)
    print("Downloading title.basics.tsv.gz...")
    with requests.get(basics_url, stream=True) as r:
        r.raise_for_status()
        with open(basics_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                
    print("Downloading title.ratings.tsv.gz...")
    with requests.get(ratings_url, stream=True) as r:
        r.raise_for_status()
        with open(ratings_file, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                
    # 3. Process and Convert to Parquet using PURE DUCKDB
    print("Processing data and converting to Parquet with DuckDB...")
    con = duckdb.connect()
    
    # DuckDB can read .gz files directly! 
    # read_csv_auto automatically detects the schema and handles the gzip compression.
    # We use COALESCE to turn SQL NULLs back into the string '\N' so your Streamlit app doesn't break.
    con.execute("""
        COPY (
            SELECT 
                b.tconst,
                COALESCE(b.primaryTitle, '\\N') as primaryTitle,
                COALESCE(b.originalTitle, '\\N') as originalTitle,
                COALESCE(b.titleType, '\\N') as titleType,
                COALESCE(b.startYear::VARCHAR, '\\N') as startYear,
                COALESCE(b.endYear::VARCHAR, '\\N') as endYear,
                COALESCE(b.runtimeMinutes::VARCHAR, '\\N') as runtimeMinutes,
                COALESCE(b.genres, '\\N') as genres,
                b.isAdult,
                COALESCE(r.averageRating::VARCHAR, '\\N') as averageRating,
                COALESCE(r.numVotes::VARCHAR, '\\N') as numVotes
            FROM read_csv_auto('title.basics.tsv.gz') b
            LEFT JOIN read_csv_auto('title.ratings.tsv.gz') r
            USING (tconst)
            WHERE b.titleType IN ('movie', 'tvMovie', 'tvSeries', 'tvMiniSeries')
        ) TO 'imdb_cache.parquet' (FORMAT PARQUET);
    """)
    print("Parquet file created successfully!")
    
    # 4. Upload to Hugging Face
    hf_token = os.environ.get("HF_TOKEN")
    repo_id = os.environ.get("HF_REPO_ID")
    
    if not hf_token or not repo_id:
        print("ERROR: HF_TOKEN or HF_REPO_ID environment variables are not set!")
        sys.exit(1)
        
    print(f"Uploading to Hugging Face repo: {repo_id}...")
    try:
        login(token=hf_token)
        api = HfApi()
        api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
        
        api.upload_file(
            path_or_fileobj=parquet_file,
            path_in_repo=parquet_file,
            repo_id=repo_id,
            repo_type="dataset",
        )
        print("Upload complete! Check Hugging Face.")
    except Exception as e:
        print(f"ERROR: Failed to upload to Hugging Face: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
