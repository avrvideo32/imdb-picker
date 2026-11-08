# IMDb Picker

A Streamlit app for exploring IMDb titles with configurable filters and controlled randomness. The app queries a Parquet copy of IMDb's public non-commercial datasets using DuckDB.

## Features

- Filter by title type, genre, decade, exact year, IMDb rating, vote count, runtime and title text.
- Choose whether multiple included genres mean **Any** (OR) or **All** (AND).
- Use **Standard Random** to select a random batch from the filtered pool.
- Use **Discovery** to balance popularity, rating, decade, genre, original-title region and original-title language where available.
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

Only title IDs are imported. The CSV is transmitted to the Streamlit app server so the IDs can be parsed; the application code does not write the original CSV to disk or forward it to IMDb, Trakt or another third party. Only upload lists to an app instance you trust or control. Watched IDs marked manually during the current app session can be downloaded as a CSV and imported again later.

## How Discovery works

Discovery first applies all active filters, then calculates popularity and rating quartiles over the complete eligible pool. It draws a bounded random candidate sample (at least 4,000 and at most 20,000 titles, scaled with the requested batch size) and greedily selects titles that fill underrepresented categories across six dimensions:

- IMDb vote-count quartile (less popular through more popular).
- IMDb rating quartile (lower through higher rated).
- Release decade.
- IMDb genre tags. Multi-genre titles can contribute to more than one genre.
- Original-title region from IMDb's `title.akas` data.
- Original-title language from the same original-title record.

The **Diversity strength** slider controls the trade-off. At 0, picks are random from the candidate sample. At 100, the selector strongly favors categories not yet represented in the current batch. Intermediate values mix both approaches.

The region is an original-title metadata region, **not a verified production country**. IMDb's public non-commercial datasets do not provide a production-country field. The app deliberately avoids presenting title-release regions as production countries.

The sort dropdown is applied after the diverse batch is selected. It changes the order, not the selection criteria, and it does not rank the entire eligible database or guarantee that globally highest-rated titles are returned.

## Refresh the IMDb dataset

The weekly GitHub Actions workflow runs scripts/update_imdb.py. Configure these repository secrets:

- HF_TOKEN: a Hugging Face token with permission to write to the dataset repository.
- HF_REPO_ID: the target dataset repository ID, for example Avrozavr/Imdb.

The updater downloads IMDb's title.basics, title.ratings and title.akas files with retries and timeouts, builds a temporary Parquet file, extracts the region and language for original-title entries, validates the schema and unique title IDs, and only then uploads it. The additional title.akas download is substantially larger than the ratings file. After deploying the new code, run the **Weekly IMDb Dataset Update** workflow once from GitHub Actions to populate the new region/language columns; the app remains compatible with the older cache until then. A failed download or validation does not publish a partial dataset.

## Notes

- user_defaults.json is stored on the app server. On a shared deployment, saved defaults are shared by visitors; they are not private per-user preferences.
- IMDb datasets are provided for personal and non-commercial use. Review IMDb's dataset terms before redistributing or using the data commercially.
