import os
import requests
import pandas as pd
from huggingface_hub import HfApi, login

def main():
    # 1. Define URLs and file paths
    basics_url = "https://datasets.imdbws.com/title.basics.tsv.gz"
    ratings_url = "https://datasets.imdbws.com/title.ratings.tsv.gz"
    
    basics_file = "title.basics.tsv.gz"
    ratings_file = "title.ratings.tsv.gz"
    parquet_file = "imdb_cache.parquet"
    
    # 2. Download files
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
                
    # 3. Read into Pandas
    print("Reading TSV files...")
    df_basics = pd.read_csv(basics_file, sep='\t', compression='gzip', dtype=str)
    df_ratings = pd.read_csv(ratings_file, sep='\t', compression='gzip', dtype=str)
    
    # Replace actual NaNs with the string '\N' to match IMDb format exactly
    df_basics = df_basics.fillna('\\N')
    df_ratings = df_ratings.fillna('\\N')
    
    # 4. Merge datasets
    print("Merging datasets...")
    df_merged = pd.merge(df_basics, df_ratings, on='tconst', how='left')
    
    # Fill missing ratings (for titles without ratings) with '\N'
    df_merged['averageRating'] = df_merged['averageRating'].fillna('\\N').astype(str)
    df_merged['numVotes'] = df_merged['numVotes'].fillna('\\N').astype(str)
    
    # 5. Save to Parquet
    print(f"Saving to {parquet_file}...")
    df_merged.to_parquet(parquet_file, index=False, engine='pyarrow')
    
    # 6. Upload to Hugging Face
    hf_token = os.environ.get("HF_TOKEN")
    repo_id = os.environ.get("HF_REPO_ID")
    
    if not hf_token or not repo_id:
        print("HF_TOKEN or HF_REPO_ID environment variables not set. Skipping upload.")
        return
        
    print(f"Uploading to Hugging Face repo: {repo_id}...")
    login(token=hf_token)
    api = HfApi()
    
    try:
        # Create the repo if it doesn't exist
        api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
        
        api.upload_file(
            path_or_fileobj=parquet_file,
            path_in_repo=parquet_file,
            repo_id=repo_id,
            repo_type="dataset",
        )
        print("Upload complete!")
    except Exception as e:
        print(f"Failed to upload: {e}")

if __name__ == "__main__":
    main()
