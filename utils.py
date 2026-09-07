GENRES = [
    "Action", "Adult", "Adventure", "Animation", "Biography", "Comedy", "Crime",
    "Documentary", "Drama", "Family", "Fantasy", "Film-Noir", "Game-Show",
    "History", "Horror", "Music", "Musical", "Mystery", "News", "Reality-TV",
    "Romance", "Sci-Fi", "Sport", "Talk-Show", "Thriller", "War", "Western",
]

TITLE_TYPES = ["movie", "tvMovie", "tvSeries", "tvMiniSeries"]
DEFAULT_TYPES = tuple(TITLE_TYPES)
DECADES = ["Any"] + [str(year) for year in range(2020, 1899, -10)]

TYPE_MAP = {
    "movie": "Movie",
    "short": "Short",
    "tvMovie": "TV Movie",
    "tvSeries": "TV Series",
    "tvMiniSeries": "TV Mini-Series",
    "tvEpisode": "TV Episode",
    "tvShort": "TV Short",
    "video": "Video",
    "videoGame": "Video Game",
}


def _missing(value):
    return value is None or str(value).strip() in {"", r"\N", "nan", "None"}


def format_runtime(runtime_value, as_hms=False):
    if _missing(runtime_value):
        return None
    try:
        minutes = int(float(runtime_value))
    except (TypeError, ValueError):
        return None

    if minutes <= 0:
        return None

    if as_hms:
        hours, mins = divmod(minutes, 60)
        return f"{hours}h {mins}m" if hours else f"{mins}m"
    return f"{minutes} min"


def format_votes(votes_value):
    if _missing(votes_value):
        return "0"
    try:
        return f"{int(float(votes_value)):,}"
    except (TypeError, ValueError):
        return "0"


def format_rating(rating_value):
    if _missing(rating_value):
        return "N/A"
    try:
        return f"{float(rating_value):.1f}"
    except (TypeError, ValueError):
        return "N/A"
