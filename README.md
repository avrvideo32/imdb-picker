# IMDb Picker

A Streamlit app for exploring IMDb titles with configurable filters and controlled randomness. The app queries a Parquet copy of IMDb's public non-commercial datasets using DuckDB.

## Features

- Filter by title type, genre, decade, exact year, IMDb rating, vote count, runtime and title text.
- Choose whether multiple included genres mean **Any** (OR) or **All** (AND).
- Use **Standard Random** to select a random batch from the filtered pool.
- Use **Discovery** to sample across four popularity quartiles, balancing lesser-known and widely rated titles.
- Sort the generated batch by rating, votes, year, runtime or title.
- Import an IMDb watched-list CSV (the standard IMDb export includes a Const column) and exclude those titles.
- Replace one pick without regenerating the rest of the batch.
- Keep titles in a shortlist, mark titles as watched, and export picks, shortlist and watched IMDb IDs to CSV.

## Run locally

    git clone https://github.com/avrvideo32/imdb-picker.git
    cd imdb-picker
    python -m pip install -r requirements.txt
    streamlit run app.py

The app reads imdb_cache.parquet from the Hugging Face dataset configured in app.py.

## Watched-list import

Export a list from IMDb as CSV and upload it in the sidebar under **Watched titles**. The file must include a column containing IMDb title IDs; IMDb's own export names this column Const.

Only title IDs are imported. The app does not connect to IMDb, Trakt or another account, and it does not upload the CSV. Watched IDs marked manually during the current app session can be downloaded as a CSV and imported again later.

## How Discovery works

Discovery first applies all the active filters. It then divides the eligible pool into four similarly sized groups based on IMDb vote count, from the least-voted quartile to the most-voted quartile. It samples in a round-robin pattern across those groups, with random selection inside each group.

The sort dropdown only changes the order of the selected batch. It does not rank the entire eligible database or guarantee that the globally highest-rated titles are returned.

## Refresh the IMDb dataset

The weekly GitHub Actions workflow runs scripts/update_imdb.py. Configure these repository secrets:

- HF_TOKEN: a Hugging Face token with permission to write to the dataset repository.
- HF_REPO_ID: the target dataset repository ID, for example Avrozavr/Imdb.

The updater downloads IMDb's title.basics and title.ratings files with retries and timeouts, builds a temporary Parquet file, validates that it contains unique title IDs, and only then uploads it. A failed download or validation does not publish a partial dataset.

## Notes

- user_defaults.json is stored on the app server. On a shared deployment, saved defaults are shared by visitors; they are not private per-user preferences.
- IMDb datasets are provided for personal and non-commercial use. Review IMDb's dataset terms before redistributing or using the data commercially.
