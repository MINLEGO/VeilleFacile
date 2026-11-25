import pytest

from veillefacile.urls import canonicalize

CASES = [
    ("https://www.youtube.com/watch?v=abc123&t=42s&list=x", "https://youtube.com/watch?v=abc123", "youtube.com"),
    ("https://youtu.be/abc123?si=zzz", "https://youtube.com/watch?v=abc123", "youtube.com"),
    ("https://m.youtube.com/shorts/abc123", "https://youtube.com/watch?v=abc123", "youtube.com"),
    ("https://github.com/Foo/Bar/blob/main/README.md#intro", "https://github.com/foo/bar", "github.com"),
    ("http://www.github.com/foo/bar/issues/3/?utm_source=x", "https://github.com/foo/bar", "github.com"),
    ("https://huggingface.co/org/model/tree/main", "https://huggingface.co/org/model", "huggingface.co"),
    ("https://huggingface.co/datasets/org/ds/viewer", "https://huggingface.co/datasets/org/ds", "huggingface.co"),
    ("https://huggingface.co/spaces/org/app?ref=x", "https://huggingface.co/spaces/org/app", "huggingface.co"),
    ("https://www.Blog.example.com/post/?utm_medium=a&fbclid=b&ref=c&id=7#top", "https://blog.example.com/post?id=7",
     "blog.example.com"),
    ("https://example.com/", "https://example.com", "example.com"),
]


@pytest.mark.parametrize("raw,canonical,site", CASES)
def test_canonicalize(raw, canonical, site):
    assert canonicalize(raw) == (canonical, site)
