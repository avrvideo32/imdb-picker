GENRES = [
    "Action", "Adult", "Adventure", "Animation", "Biography", "Comedy", "Crime",
    "Documentary", "Drama", "Family", "Fantasy", "Film-Noir", "Game-Show", "History",
    "Horror", "Music", "Musical", "Mystery", "News", "Reality-TV", "Romance",
    "Sci-Fi", "Sport", "Talk-Show", "Thriller", "War", "Western"
]

TITLE_TYPES = ["movie", "tvMovie", "tvSeries", "tvMiniSeries"]
DEFAULT_TYPES = {"movie", "tvMovie", "tvSeries", "tvMiniSeries"}

DECADES = ["Any"] + [str(y) for y in range(2020, 1899, -10)]

TYPE_MAP = {
    'movie': 'Movie', 'short': 'Short', 'tvMovie': 'TV Movie',
    'tvSeries': 'TV Series', 'tvMiniSeries': 'TV Mini-Series',
    'tvEpisode': 'TV Episode', 'tvShort': 'TV Short',
    'video': 'Video', 'videoGame': 'Video Game'
}

def format_runtime(runtime_str, as_hms=False):
    if not runtime_str or runtime_str == '\\N':
        return None
    try:
        rt = int(runtime_str)
    except ValueError:
        return None
    
    if as_hms and rt:
        h, m = divmod(rt, 60)
        return f"{h}h {m}m" if h else f"{m}m"
    elif rt:
        return f"{rt} min"
    return None

def format_votes(votes_str):
    if votes_str and votes_str != '\\N':
        try:
            return f"{int(votes_str):,}"
        except ValueError:
            pass
    return "0"

def format_rating(rating_str):
    if rating_str and rating_str != '\\N':
        try:
            return f"{float(rating_str):.1f}"
        except ValueError:
            pass
    return "N/A"GENRES = [
    "Action", "Adult", "Adventure", "Animation", "Biography", "Comedy", "Crime",
    "Documentary", "Drama", "Family", "Fantasy", "Film-Noir", "Game-Show", "History",
    "Horror", "Music", "Musical", "Mystery", "News", "Reality-TV", "Romance",
    "Sci-Fi", "Sport", "Talk-Show", "Thriller", "War", "Western"
]

TITLE_TYPES = [
    "movie", "tvMovie", "tvSeries", "tvMiniSeries", "short", 
    "tvEpisode", "tvShort", "video", "videoGame"
]

DEFAULT_TYPES = ["movie", "tvMovie", "tvSeries", "tvMiniSeries"]

DECADES = ["Any"] + [str(y) for y in range(2020, 1899, -10)]

TYPE_MAP = {
    'movie': 'Movie', 'short': 'Short', 'tvMovie': 'TV Movie',
    'tvSeries': 'TV Series', 'tvMiniSeries': 'TV Mini-Series',
    'tvEpisode': 'TV Episode', 'tvShort': 'TV Short',
    'video': 'Video', 'videoGame': 'Video Game'
}

def format_runtime(runtime_str, as_hms=False):
    """Convert runtime string from DB to display format."""
    if not runtime_str or runtime_str == '\\N':
        return None
    try:
        rt = int(runtime_str)
    except ValueError:
        return None
    
    if as_hms and rt:
        h, m = divmod(rt, 60)
        return f"{h}h {m}m" if h else f"{m}m"
    elif rt:
        return f"{rt} min"
    return None

def format_votes(votes_str):
    if votes_str and votes_str != '\\N':
        try:
            return f"{int(votes_str):,}"
        except ValueError:
            pass
    return "0"

def format_rating(rating_str):
    if rating_str and rating_str != '\\N':
        try:
            return f"{float(rating_str):.1f}"
        except ValueError:
            pass
    return "N/A"
