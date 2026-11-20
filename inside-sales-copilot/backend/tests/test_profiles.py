import json

import pytest

from backend.src.lib import profiles as p

GOOD = {
    "a.b@example-co.com": {
        "name": "A B", "employer": "Example Co", "employer_domain": "example-co.com",
        "title": "Director", "source_url": "synthetic://profiles",
    }
}


def dump(data) -> str:
    return json.dumps(data)


def test_real_profile_file_is_valid_and_synthetic():
    profiles = p.load_profiles()
    assert profiles, "profile file must not be empty"
    assert all(x.source_url == "synthetic://profiles" for x in profiles.values())
    assert all(email == email.lower() for email in profiles)


def test_parses_a_good_profile():
    loaded = p.parse_profiles(dump(GOOD))
    assert loaded["a.b@example-co.com"].employer == "Example Co"


def test_lookup_is_case_insensitive_and_trims():
    loaded = p.parse_profiles(dump(GOOD))
    assert p.lookup(loaded, "  A.B@Example-Co.com ") is not None
    assert p.lookup(loaded, "nobody@example-co.com") is None
    assert p.lookup(loaded, None) is None
    assert p.lookup(loaded, "") is None


def test_duplicate_email_is_rejected():
    text = (
        '{"a.b@example-co.com": %s, "a.b@example-co.com": %s}'
        % (dump(GOOD["a.b@example-co.com"]), dump(GOOD["a.b@example-co.com"]))
    )
    with pytest.raises(p.ProfileError, match="duplicate"):
        p.parse_profiles(text)


def test_duplicate_email_differing_only_in_case_is_rejected():
    entry = dump(GOOD["a.b@example-co.com"])
    text = '{"a.b@example-co.com": %s, "A.B@example-co.com": %s}' % (entry, entry)
    with pytest.raises(p.ProfileError):
        p.parse_profiles(text)


@pytest.mark.parametrize("change", [
    {"source_url": "https://www.linkedin.com/in/someone"},
    {"source_url": ""},
    {"title": "  "},
    {"employer_domain": "Not A Domain"},
    {"employer_domain": "UPPER.com"},
])
def test_bad_field_is_rejected(change):
    entry = {**GOOD["a.b@example-co.com"], **change}
    with pytest.raises(p.ProfileError):
        p.parse_profiles(dump({"a.b@example-co.com": entry}))


def test_missing_and_extra_fields_are_rejected():
    no_title = {k: v for k, v in GOOD["a.b@example-co.com"].items() if k != "title"}
    with pytest.raises(p.ProfileError):
        p.parse_profiles(dump({"a.b@example-co.com": no_title}))
    with pytest.raises(p.ProfileError):
        p.parse_profiles(dump({"a.b@example-co.com": {**GOOD["a.b@example-co.com"], "linkedin": "x"}}))


def test_key_must_be_a_lowercase_email():
    with pytest.raises(p.ProfileError):
        p.parse_profiles(dump({"A.B@example-co.com": GOOD["a.b@example-co.com"]}))
    with pytest.raises(p.ProfileError):
        p.parse_profiles(dump({"not-an-email": GOOD["a.b@example-co.com"]}))


def test_invalid_json_and_wrong_top_level_are_rejected():
    with pytest.raises(p.ProfileError):
        p.parse_profiles("{not json")
    with pytest.raises(p.ProfileError):
        p.parse_profiles("[]")
