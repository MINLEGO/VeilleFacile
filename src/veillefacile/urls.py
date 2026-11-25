import re
from urllib.parse import parse_qsl, urlencode, urlsplit

_YT_HOSTS = {"youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"}
_TRACKING = re.compile(r"^(utm_.*|fbclid|ref)$", re.I)


def canonicalize(raw: str) -> tuple[str, str]:
    """Raw URL -> (canonical URL, origin site). Canonical URLs are always https, without www/fragment/trailing slash."""
    u = urlsplit(raw.strip())
    host = (u.hostname or "").lower().removeprefix("www.")
    parts = [p for p in u.path.split("/") if p]
    query = parse_qsl(u.query, keep_blank_values=True)
    if host in _YT_HOSTS:
        vid = parts[0] if host == "youtu.be" and parts else None
        if parts and parts[0] in ("shorts", "embed", "live", "v") and len(parts) > 1:
            vid = parts[1]
        vid = vid or dict(query).get("v")
        if vid:
            return f"https://youtube.com/watch?v={vid}", "youtube.com"
    if host == "github.com" and len(parts) >= 2:
        return f"https://github.com/{parts[0]}/{parts[1]}".lower(), host
    if host == "huggingface.co" and parts:
        n = 3 if parts[0] in ("datasets", "spaces") else 2
        if len(parts) >= n:
            return "https://huggingface.co/" + "/".join(parts[:n]), host
    kept = urlencode([(k, v) for k, v in query if not _TRACKING.match(k)])
    return f"https://{host}{u.path.rstrip('/')}" + (f"?{kept}" if kept else ""), host
