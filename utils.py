GENRES = [
    "Action", "Adult", "Adventure", "Animation", "Biography", "Comedy", "Crime",
    "Documentary", "Drama", "Family", "Fantasy", "Film-Noir", "Game-Show", "History",
    "Horror", "Music", "Musical", "Mystery", "News", "Reality-TV", "Romance",
    "Sci-Fi", "Sport", "Talk-Show", "Thriller", "War", "Western"
]

TITLE_TYPES = [
    "movie", "short", "tvMovie", "tvSeries", "tvMiniSeries",
    "tvEpisode", "tvShort", "video", "videoGame"
]

DEFAULT_TYPES = {"movie", "tvMovie", "tvSeries", "tvMiniSeries"}

DECADES = ["Any"] + [str(y) for y in range(2020, 1899, -10)]

DEFAULT_STATE = {
    'min_votes': "50",
    'min_rating': "",
    'year': "",
    'decade': "Any",
    'search': "",
    'fuzzy': False,
    'runtime_min': "",
    'runtime_max': "",
    'adult': True,
    'runtime_fmt': False,
    'num_picks': 8
}


def format_runtime(runtime_str, as_hms=False):
    """Convert runtime string from DB to display format."""
    if not runtime_str or runtime_str == '\\N':
        return runtime_str

    try:
        rt = int(runtime_str)
    except ValueError:
        return runtime_str

    if as_hms and rt:
        h, m = divmod(rt, 60)
        return f"{h}h {m}m" if h else f"{m}m"
    elif rt:
        return f"{rt} min"
    return runtime_str


def format_votes(votes_str):
    if votes_str and votes_str != '\\N':
        try:
            return f"{int(votes_str):,}"
        except ValueError:
            return votes_str
    return ''


def format_rating(rating_str):
    if rating_str and rating_str != '\\N':
        try:
            return f"{float(rating_str):.1f}"
        except ValueError:
            return rating_str
    return ''