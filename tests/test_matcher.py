from matcher import build_query, matches_tweet


def settings():
    return {
        "search": {
            "language": "en",
            "ignore_retweets": True,
            "ignore_replies": False,
        },
        "matcher": {
            "timing_phrases": ["what time", "what time does", "when is", "when does"],
            "fighter_names": ["Haney"],
            "target_terms": ["main event", "ring walk"],
        },
    }


def test_query_contains_expected_parts():
    query = build_query(settings())
    assert "what time" in query
    assert "Haney" in query
    assert "-is:retweet" in query
    assert "lang:en" in query


def test_matches_tweet_for_timing_and_target():
    assert matches_tweet("What time is the Haney main event tonight?", settings())


def test_rejects_without_timing_phrase():
    assert not matches_tweet("Haney is walking out now", settings())


def test_rejects_without_target_phrase():
    assert not matches_tweet("What time does it start tonight?", settings())


def test_rejects_generic_when_without_timing_phrase():
    assert not matches_tweet("when bianca returns to the main event next month", settings())
