import os
import sys
import tempfile
from pathlib import Path

import duckdb


BASICS_URL = "https://datasets.imdbws.com/title.basics.tsv.gz"
RATINGS_URL = "https://datasets.imdbws.com/title.ratings.tsv.gz"
AKAS_URL = "https://datasets.imdbws.com/title.akas.tsv.gz"


def build_session():
    import requests
    from requests.adapters import HTTPAdapter
    from urllib3.util.retry import Retry

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


def create_dataset(basics_file, ratings_file, akas_file, parquet_file):
    print("Processing IMDb data and building original-title region/language metadata...")
    con = duckdb.connect()
    try:
        basics_path = str(basics_file).replace("\\", "/").replace("'", "''")
        ratings_path = str(ratings_file).replace("\\", "/").replace("'", "''")
        akas_path = str(akas_file).replace("\\", "/").replace("'", "''")
        parquet_path = str(parquet_file).replace("\\", "/").replace("'", "''")

        con.execute(
            f"""
            COPY (
                WITH aka_metadata AS (
                    SELECT
                        titleId,
                        arg_min(
                            NULLIF(region, '\\N'),
                            TRY_CAST(ordering AS INTEGER)
                        ) FILTER (
                            WHERE region IS NOT NULL AND region <> '\\N'
                        ) AS originalTitleRegion,
                        arg_min(
                            NULLIF(language, '\\N'),
                            TRY_CAST(ordering AS INTEGER)
                        ) FILTER (
                            WHERE language IS NOT NULL AND language <> '\\N'
                        ) AS originalTitleLanguage
                    FROM read_csv_auto('{akas_path}', delim='\\t')
                    GROUP BY titleId
                )
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
                    COALESCE(r.numVotes::VARCHAR, '\\N') AS numVotes,
                    COALESCE(a.originalTitleRegion, '\\N') AS originalTitleRegion,
                    COALESCE(a.originalTitleLanguage, '\\N') AS originalTitleLanguage
                FROM read_csv_auto('{basics_path}', delim='\\t') b
                LEFT JOIN read_csv_auto('{ratings_path}', delim='\\t') r
                    USING (tconst)
                LEFT JOIN aka_metadata a
                    ON a.titleId = b.tconst
                WHERE b.titleType IN ('movie', 'tvMovie', 'tvSeries', 'tvMiniSeries')
            ) TO '{parquet_path}' (FORMAT PARQUET);
            """
        )

        parquet_ref = f"read_parquet('{parquet_path}')"
        row_count = con.execute(
            f"SELECT COUNT(*) FROM {parquet_ref}"
        ).fetchone()[0]
        if row_count <= 0:
            raise RuntimeError("The generated Parquet dataset contains no titles.")

        distinct_ids = con.execute(
            f"SELECT COUNT(DISTINCT tconst) FROM {parquet_ref}"
        ).fetchone()[0]
        if distinct_ids != row_count:
            raise RuntimeError(
                "Dataset validation failed: IMDb title IDs are not unique."
            )

        columns = {
            row[0] for row in con.execute(
                f"DESCRIBE SELECT * FROM {parquet_ref}"
            ).fetchall()
        }
        required = {
            "tconst", "primaryTitle", "genres", "averageRating", "numVotes",
            "originalTitleRegion", "originalTitleLanguage",
        }
        missing = required - columns
        if missing:
            raise RuntimeError(
                "Dataset validation failed; missing columns: "
                + ", ".join(sorted(missing))
            )

        region_count, language_count = con.execute(
            f"""
            SELECT
                COUNT(*) FILTER (
                    WHERE originalTitleRegion IS NOT NULL
                      AND originalTitleRegion <> '\\N'
                ),
                COUNT(*) FILTER (
                    WHERE originalTitleLanguage IS NOT NULL
                      AND originalTitleLanguage <> '\\N'
                )
            FROM {parquet_ref}
            """
        ).fetchone()

        if region_count == 0 and language_count == 0:
            raise RuntimeError(
                "Dataset validation failed: IMDb title.akas contains no usable "
                "region or language metadata. Refusing to publish an empty "
                "geographic/language dataset."
            )

        size = Path(parquet_file).stat().st_size
        if size <= 0:
            raise RuntimeError("The generated Parquet file is empty.")

        print(
            f"Dataset validated: {row_count:,} titles, "
            f"{region_count:,} with an original-title region, "
            f"{language_count:,} with an original-title language, "
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
        akas_file = temp_path / "title.akas.tsv.gz"
        parquet_file = temp_path / "imdb_cache.parquet"

        session = build_session()
        try:
            download_file(session, BASICS_URL, basics_file)
            download_file(session, RATINGS_URL, ratings_file)
            download_file(session, AKAS_URL, akas_file)
        finally:
            session.close()

        create_dataset(basics_file, ratings_file, akas_file, parquet_file)

        print(f"Uploading validated dataset to Hugging Face repo: {repo_id}...")
        try:
            from huggingface_hub import HfApi, login

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
