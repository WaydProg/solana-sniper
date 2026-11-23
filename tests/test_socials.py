from datetime import datetime, timezone

import pytest

from sniper.check_methods.socials import (normalize_url, extract_socials, twitter_username, telegram_chat,
                                          evaluate_twitter_user, check_socials_present, check_reused_socials)
from sniper.clients.apis import metadata_urls


@pytest.mark.parametrize("raw,expected", [
    ("https://twitter.com/Foo/", "https://x.com/Foo"),
    ("www.x.com/foo?s=20", "https://x.com/foo"),
    ("@foo", "https://x.com/foo"),
    ("telegram.me/chat", "https://t.me/chat"),
    ("", None),
    (None, None),
    ("not a url", None),
])
def test_normalize_url(raw, expected):
    assert normalize_url(raw) == expected


def test_extract_socials_classifies_by_domain():
    socials = extract_socials({
        "twitter": "https://x.com",  # заглушка без пути
        "website": "https://t.me/realchat",
        "extensions": {"twitter": "https://x.com/project"},
    })
    assert socials.twitter == "https://x.com/project"
    assert socials.telegram == "https://t.me/realchat"
    assert socials.website is None


@pytest.mark.parametrize("url,expected", [
    ("https://x.com/project", "project"),
    ("https://x.com/elonmusk/status/123", "elonmusk"),
    ("https://x.com/i/communities/123", None),
    ("https://x.com/search", None),
])
def test_twitter_username(url, expected):
    assert twitter_username(url) == expected


@pytest.mark.parametrize("url,expected", [
    ("https://t.me/mychat", ("mychat", False)),
    ("https://t.me/s/mychat", ("mychat", False)),
    ("https://t.me/+AbCdEf", (None, True)),
    ("https://t.me/joinchat/AbCdEf", (None, True)),
])
def test_telegram_chat(url, expected):
    assert telegram_chat(url) == expected


def test_evaluate_twitter_user():
    now = datetime(2026, 9, 26, tzinfo=timezone.utc)
    old = {"followers": 500, "joined": "Thu Jan 11 05:47:40 +0000 2018"}
    fresh = {"followers": 500, "joined": "Thu Sep 24 05:47:40 +0000 2026"}
    few = {"followers": 3, "joined": "Thu Jan 11 05:47:40 +0000 2018"}
    assert evaluate_twitter_user("a", old, now).passed
    assert evaluate_twitter_user("a", fresh, now).passed is False
    assert evaluate_twitter_user("a", few, now).passed is False
    assert evaluate_twitter_user("a", None, now).passed is False


def test_presence_and_reuse():
    assert check_socials_present(extract_socials({})).passed is False
    assert check_reused_socials(["https://x.com/a"]).passed is False
    assert check_reused_socials([]).passed


def test_metadata_urls_adds_gateways():
    urls = metadata_urls("https://ipfs.io/ipfs/QmQVRV6bmgYGcpwgjupekJQ5ZZNHwvPjDUc7To2VgLRpt1")
    assert urls[0].startswith("https://ipfs.io/")
    assert len(urls) == len(set(urls)) > 1
    assert metadata_urls("https://example.com/meta.json") == ["https://example.com/meta.json"]
