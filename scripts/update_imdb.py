import os
import sys
import tempfile
from pathlib import Path

import duckdb
import requests
from huggingface_hub import HfApi, login
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


BASICS_URL = "https://datasets.imdbws.com/title.basics.tsv.gz"
RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"


def build_session():
    retry = Retry(
        total=5,
        connect=5,
        read=5,
        status=5,
        backoff_factor=1.5,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session = requests.Session()
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def download_file(session, url, destination):
    print(f"Downloading {url.rsplit('/', 1)[-1]}...")
    total_bytes = 0
    with session.get(url, stream=True, timeout=(30, 300)) as response:
        response.raise_for_status()
        with open(destination, "wb") as output:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                if chunk:
                    output.write(chunk)
                    total_bytes += len(chunk)

    if total_bytes == 0:
        raise RuntimeError(f"Download was empty: {url}")
    print(f"Downloaded {total_bytes:,} bytes.")


def create_dataset(basics_file, ratings_file, parquet_file):
    print("Processing IMDb data and converting it to Parquet...")
    con = duckdb.connect()
    try:
        basics_path = str(basics_file).replace("\\", "/").replace("'", "''")
        ratings_path = str(ratings_file).replace("\\", "/").replace("'", "''")
        parquet_path = str(parquet_file).replace("\\", "/").replace("'", "''")

        con.execute(
            f"""
            COPY (
                SELECT
                    b.tconst,
                    COALESCE(b.primaryTitle, '\\N') AS primaryTitle,
                    COALESCE(b.originalTitle, '\\N') AS originalTitle,
                    COALESCE(b.titleType, '\\N') AS titleType,
                    COALESCE(b.startYear::VARCHAR, '\\N') AS startYear,
                    COALESCE(b.endYear::VARCHAR, '\\N') AS endYear,
                    COALESCE(b.runtimeMinutes::VARCHAR, '\\N') AS runtimeMinutes,
                    COALESCE(b.genres, '\\N') AS genres,
                    b.isAdult,
                    COALESCE(r.averageRating::VARCHAR, '\\N') AS averageRating,
                    COALESCE(r.numVotes::VARCHAR, '\\N') AS numVotes
                FROM read_csv_auto('{basics_path}') b
                LEFT JOIN read_csv_auto('{ratings_path}') r
                USING (tconst)
                WHERE b.titleType IN ('movie', 'tvMovie', 'tvSeries', 'tvMiniSeries')
            ) TO '{parquet_path}' (FORMAT PARQUET);
            """
        )

        row_count = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{parquet_path}')"
        ).fetchone()[0]
        if row_count <= 0:
            raise RuntimeError("The generated Parquet dataset contains no titles.")

        distinct_ids = con.execute(
            f"SELECT COUNT(DISTINCT tconst) FROM read_parquet('{parquet_path}')"
        ).fetchone()[0]
        if distinct_ids != row_count:
            raise RuntimeError(
                "Dataset validation failed: IMDb title IDs are not unique."
            )

        size = Path(parquet_file).stat().st_size
        if size <= 0:
            raise RuntimeError("The generated Parquet file is empty.")

        print(
            f"Dataset validated: {row_count:,} titles, "
            f"{size / (1024 * 1024):.1f} MiB."
        )
        return row_count
    finally:
        con.close()


def main():
    hf_token = os.environ.get("HF_TOKEN")
    repo_id = os.environ.get("HF_REPO_ID")
    if not hf_token or not repo_id:
        print("ERROR: HF_TOKEN or HF_REPO_ID environment variables are not set!")
        sys.exit(1)

    # Build everything in a temporary directory. A failed download or conversion
    # therefore cannot leave a partial dataset at the upload path.
    with tempfile.TemporaryDirectory(prefix="imdb-picker-") as temp_dir:
        temp_path = Path(temp_dir)
        basics_file = temp_path / "title.basics.tsv.gz"
        ratings_file = temp_path / "title.ratings.tsv.gz"
        parquet_file = temp_path / "imdb_cache.parquet"

        session = build_session()
        try:
            download_file(session, BASICS_URL, basics_file)
            download_file(session, RATINGS_URL, ratings_file)
        finally:
            session.close()

        create_dataset(basics_file, ratings_file, parquet_file)

        print(f"Uploading validated dataset to Hugging Face repo: {repo_id}...")
        try:
            login(token=hf_token)
            api = HfApi()
            api.create_repo(repo_id=repo_id, repo_type="dataset", exist_ok=True)
            api.upload_file(
                path_or_fileobj=str(parquet_file),
                path_in_repo="imdb_cache.parquet",
                repo_id=repo_id,
                repo_type="dataset",
            )
            print("Upload complete! The published dataset was replaced.")
        except Exception as exc:
            print(f"ERROR: Failed to upload to Hugging Face: {exc}")
            sys.exit(1)


if __name__ == "__main__":
    main()
