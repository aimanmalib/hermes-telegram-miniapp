"""initData verification against https://core.telegram.org/bots/webapps."""

from __future__ import annotations

import base64
import hmac
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from conftest import BOT_TOKEN, OWNER_ID, USER_JSON, encode, make_init_data

NOW = 1_760_000_000
ALLOWED = [str(OWNER_ID)]

# Known-answer vectors computed independently with openssl:
#   secret = HMAC-SHA256(key="WebAppData", msg=BOT_TOKEN)
#   hash   = HMAC-SHA256(key=secret, msg=data_check_string)
KAT_SECRET = "998cdc0cc799d2fe4fd5f8c0d5f545463538b8f23fe79e6e8521b533ed05f0bc"  # gitleaks:allow (derived from the fake BOT_TOKEN)
KAT_FIELDS = {
    "auth_date": "1760000000",
    "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
    "user": USER_JSON,
}
KAT_HASH = "803a862d73d0cd2b0d89102b82591a5e933e90b3c33df998ef0746edbe8ccc5e"
KAT_SIG_FIELD = "c2lnbmF0dXJlLXBsYWNlaG9sZGVy"
KAT_HASH_WITH_SIGNATURE = "b04ac8c970da2845267ae4fcc42851902b21572d2b2a128d01f7e502070060ba"


def verify(tg_auth, init_data, **kw):
    kw.setdefault("bot_token", BOT_TOKEN)
    kw.setdefault("allowed_user_ids", ALLOWED)
    kw.setdefault("now", NOW)
    return tg_auth.verify_init_data(init_data, **kw)


def reason(tg_auth, init_data, **kw):
    with pytest.raises(tg_auth.InitDataError) as exc:
        verify(tg_auth, init_data, **kw)
    return exc.value.reason


# --- known-answer ---------------------------------------------------------

def test_known_answer_hash(tg_auth):
    assert tg_auth.compute_hash(KAT_FIELDS, BOT_TOKEN) == KAT_HASH
    assert USER_JSON == '{"id":424242,"first_name":"Ada","username":"ada_test","language_code":"en"}'


def test_known_answer_secret_key_derivation():
    import hashlib

    secret = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).hexdigest()
    assert secret == KAT_SECRET


def test_known_answer_signature_field_is_part_of_hmac(tg_auth):
    fields = dict(KAT_FIELDS, signature=KAT_SIG_FIELD)
    assert tg_auth.compute_hash(fields, BOT_TOKEN) == KAT_HASH_WITH_SIGNATURE
    init_data = encode(dict(fields, hash=KAT_HASH_WITH_SIGNATURE))
    assert verify(tg_auth, init_data)["id"] == OWNER_ID


def test_known_answer_full_verify(tg_auth):
    init_data = encode(dict(KAT_FIELDS, hash=KAT_HASH))
    user = verify(tg_auth, init_data)
    assert user["id"] == OWNER_ID and user["username"] == "ada_test"


# --- valid ----------------------------------------------------------------

@pytest.mark.parametrize("plus_spaces", [False, True])
def test_valid_with_either_space_encoding(tg_auth, plus_spaces):
    user = {"id": OWNER_ID, "first_name": "Ada Lovelace"}
    data = make_init_data(auth_date=NOW - 10, user=user, plus_spaces=plus_spaces)
    assert verify(tg_auth, data)["first_name"] == "Ada Lovelace"


def test_uppercase_hex_hash_accepted(tg_auth):
    data = make_init_data(auth_date=NOW)
    head, _, h = data.rpartition("hash=")
    assert verify(tg_auth, head + "hash=" + h.upper())["id"] == OWNER_ID


# --- tampering / wrong key ------------------------------------------------

def test_tampered_hash(tg_auth):
    data = make_init_data(auth_date=NOW)
    flipped = data[:-1] + ("0" if data[-1] != "0" else "1")
    assert reason(tg_auth, flipped) == "bad_signature"


def test_tampered_field(tg_auth):
    data = make_init_data(auth_date=NOW).replace("auth_date=", "auth_date=1", 1)
    assert reason(tg_auth, data) == "bad_signature"


def test_extra_field_injected_after_signing(tg_auth):
    data = make_init_data(auth_date=NOW) + "&start_param=evil"
    assert reason(tg_auth, data) == "bad_signature"


def test_wrong_bot_token(tg_auth):
    data = make_init_data(auth_date=NOW, bot_token="987654321:some-other-bot")
    assert reason(tg_auth, data) == "bad_signature"


def test_missing_hash(tg_auth):
    data = make_init_data(auth_date=NOW).rpartition("&hash=")[0]
    assert reason(tg_auth, data) == "bad_signature"


# --- freshness ------------------------------------------------------------

def test_stale_auth_date_rejected(tg_auth):
    data = make_init_data(auth_date=NOW - 3601)
    assert reason(tg_auth, data, max_age_sec=3600) == "stale"


def test_auth_date_at_window_edge_accepted(tg_auth):
    data = make_init_data(auth_date=NOW - 3600)
    assert verify(tg_auth, data, max_age_sec=3600)["id"] == OWNER_ID


def test_default_window_is_one_hour(tg_auth):
    assert tg_auth.DEFAULT_MAX_AGE_SEC == 3600
    assert reason(tg_auth, make_init_data(auth_date=NOW - 3601)) == "stale"


def test_auth_date_far_in_future_rejected(tg_auth):
    data = make_init_data(auth_date=NOW + 3600)
    assert reason(tg_auth, data) == "auth_date_in_future"


def test_small_clock_skew_tolerated(tg_auth):
    assert verify(tg_auth, make_init_data(auth_date=NOW + 30))["id"] == OWNER_ID


@pytest.mark.parametrize("value", ["", "0x10", "-5", "1e9"])
def test_missing_or_bad_auth_date_rejected(tg_auth, value):
    # Correctly signed, but auth_date is unusable: must not skip the freshness check.
    fields = {"user": USER_JSON}
    if value:
        fields["auth_date"] = value
    from conftest import spec_hash

    fields["hash"] = spec_hash(fields, BOT_TOKEN)
    assert reason(tg_auth, encode(fields)) == "auth_date_missing"


def test_auth_date_zero_is_stale_not_skipped(tg_auth):
    assert reason(tg_auth, make_init_data(auth_date=0)) == "stale"


# --- allowlist ------------------------------------------------------------

def test_non_owner_rejected(tg_auth):
    data = make_init_data(auth_date=NOW, user={"id": 777, "first_name": "Eve"})
    assert reason(tg_auth, data) == "not_allowed"


def test_empty_allowlist_fails_closed(tg_auth):
    data = make_init_data(auth_date=NOW)
    assert reason(tg_auth, data, allowed_user_ids=[]) == "allowlist_unset"
    assert reason(tg_auth, data, allowed_user_ids=["", " "]) == "allowlist_unset"


def test_missing_bot_token_fails_closed(tg_auth):
    assert reason(tg_auth, make_init_data(auth_date=NOW), bot_token="") == "bot_token_unset"


def test_second_allowed_user_accepted(tg_auth):
    data = make_init_data(auth_date=NOW, user={"id": 555})
    assert verify(tg_auth, data, allowed_user_ids=["1", "555"])["id"] == 555


# --- malformed ------------------------------------------------------------

@pytest.mark.parametrize(
    "payload,expected",
    [
        ("", "empty"),
        ("x" * 9000, "too_long"),
        ("no-equals-sign", "malformed"),
        ("a=1&&b=2", "malformed"),
    ],
)
def test_malformed_payloads(tg_auth, payload, expected):
    assert reason(tg_auth, payload) == expected


def test_duplicate_keys_rejected(tg_auth):
    data = make_init_data(auth_date=NOW) + "&user=%7B%22id%22%3A1%7D"
    assert reason(tg_auth, data) == "duplicate_key"


def test_non_ascii_hash_does_not_raise_type_error(tg_auth):
    data = make_init_data(auth_date=NOW).rpartition("&hash=")[0] + "&hash=%C3%A9"
    assert reason(tg_auth, data) == "bad_signature"


@pytest.mark.parametrize(
    "user_value",
    ["not-json", "[1,2]", '{"id":"424242"}', '{"id":true}', '{"first_name":"x"}', "null"],
)
def test_malformed_user_rejected(tg_auth, user_value):
    from conftest import spec_hash

    fields = {"auth_date": str(NOW), "user": user_value}
    fields["hash"] = spec_hash(fields, BOT_TOKEN)
    assert reason(tg_auth, encode(fields)) == "user_malformed"


def test_non_string_input(tg_auth):
    assert reason(tg_auth, None) == "empty"  # type: ignore[arg-type]


# --- constant-time compare ------------------------------------------------

def test_hash_compared_with_compare_digest(tg_auth, monkeypatch):
    calls = []
    real = hmac.compare_digest

    def spy(a, b):
        calls.append((type(a), type(b)))
        return real(a, b)

    monkeypatch.setattr(tg_auth.hmac, "compare_digest", spy)
    verify(tg_auth, make_init_data(auth_date=NOW))
    assert calls, "hash must be compared with hmac.compare_digest"
    assert calls[0] == (bytes, bytes)


# --- Ed25519 (third-party validation) -------------------------------------

def _keypair():
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw).hex()
    return key, pub


def test_published_ed25519_keys_match_spec(tg_auth):
    assert tg_auth.TELEGRAM_ED25519_PUBKEY_PROD == (
        "e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d"
    )
    assert tg_auth.TELEGRAM_ED25519_PUBKEY_TEST == (
        "40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec"
    )


def test_ed25519_fallback_accepts_valid_signature(tg_auth):
    key, pub = _keypair()
    # Signed for our bot id, but the HMAC was made with another token, so only
    # the Ed25519 path can accept it.
    data = make_init_data(auth_date=NOW, bot_token="1:other", ed_key=key, ed_bot_id="123456789")
    assert verify(tg_auth, data, ed25519_pubkeys=[pub])["id"] == OWNER_ID


def test_ed25519_bot_id_taken_from_token(tg_auth):
    assert tg_auth.bot_id_from_token(BOT_TOKEN) == "123456789"
    assert tg_auth.bot_id_from_token("garbage") is None


def test_ed25519_wrong_bot_id_rejected(tg_auth):
    key, pub = _keypair()
    data = make_init_data(auth_date=NOW, bot_token="1:other", ed_key=key, ed_bot_id="555")
    assert reason(tg_auth, data, ed25519_pubkeys=[pub]) == "bad_signature"


def test_ed25519_untrusted_key_rejected(tg_auth):
    key, _ = _keypair()
    data = make_init_data(auth_date=NOW, bot_token="1:other", ed_key=key, ed_bot_id="123456789")
    # Default trust = Telegram's production key only.
    assert reason(tg_auth, data) == "bad_signature"


def test_ed25519_dcs_excludes_hash_and_has_bot_prefix(tg_auth):
    fields = {"b": "2", "a": "1", "hash": "h", "signature": "s"}
    assert tg_auth.ed25519_data_check_string(fields, "42") == "42:WebAppData\na=1\nb=2"


def test_ed25519_signature_over_hash_rejected(tg_auth):
    # The pre-fix implementation signed hash into the DCS and had no bot prefix.
    key, pub = _keypair()
    fields = {"auth_date": str(NOW), "user": USER_JSON, "hash": "00" * 32}
    wrong = "\n".join(f"{k}={fields[k]}" for k in sorted(fields)).encode()
    fields["signature"] = base64.urlsafe_b64encode(key.sign(wrong)).rstrip(b"=").decode()
    assert reason(tg_auth, encode(fields), ed25519_pubkeys=[pub]) == "bad_signature"


def test_ed25519_garbage_signature(tg_auth):
    fields = {"auth_date": str(NOW), "user": USER_JSON, "signature": "!!!", "hash": "00"}
    assert reason(tg_auth, encode(fields)) == "bad_signature"


# --- config parsing + limiter ---------------------------------------------

@pytest.mark.parametrize(
    "raw,expected",
    [(None, 3600), ("", 3600), ("abc", 3600), ("5", 60), ("900", 900), ("99999999", 604800)],
)
def test_parse_max_age(tg_auth, raw, expected):
    assert tg_auth.parse_max_age(raw) == expected


def test_parse_allowlist(tg_auth):
    assert tg_auth.parse_allowlist(" 1, 22 ,abc,,-3 ") == ("1", "22")
    assert tg_auth.parse_allowlist(None) == ()


def test_failure_limiter_blocks_and_recovers(tg_auth):
    t = [0.0]
    lim = tg_auth.FailureLimiter(max_failures=3, window_sec=60, clock=lambda: t[0])
    for _ in range(3):
        assert lim.retry_after("ip") == 0
        lim.record_failure("ip")
    assert lim.retry_after("ip") > 0
    assert lim.retry_after("other") == 0
    t[0] = 61
    assert lim.retry_after("ip") == 0


def test_failure_limiter_bounded_memory(tg_auth):
    lim = tg_auth.FailureLimiter(max_failures=3, window_sec=60, max_keys=5)
    for i in range(50):
        lim.record_failure(f"k{i}")
    assert len(lim._failures) <= 5


def test_user_json_roundtrip_matches(tg_auth):
    data = make_init_data(auth_date=NOW)
    assert json.loads(tg_auth.parse_init_data(data)["user"])["id"] == OWNER_ID
