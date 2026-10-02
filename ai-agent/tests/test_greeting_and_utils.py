import pytest

from airaa.greeting import detect_greeting, get_greeting_response
from airaa.utils.assets import extract_chain, extract_symbols, to_coingecko_ids
from airaa.utils.format import fmt_money, fmt_num, fmt_pct


@pytest.mark.parametrize("text", ["hi", "Hello!", "good morning", "thanks", "thank you so much", "how are you?"])
def test_pure_small_talk_is_a_greeting(text):
    assert detect_greeting(text)


@pytest.mark.parametrize("text", [
    "hey, what's the BTC price?", "hi what is tvl of aave", "what is ethereum", "hello can you compare btc and eth", "",
])
def test_greeting_followed_by_a_real_question_is_not_a_greeting(text):
    assert not detect_greeting(text)


def test_greeting_reply_is_a_string():
    assert isinstance(get_greeting_response("hi", {"message_count": 0}), str)


def test_extract_symbols_orders_by_appearance_and_dedupes():
    assert extract_symbols("Compare Solana vs Bitcoin and BTC again") == ["SOL", "BTC"]


def test_extract_symbols_uses_word_boundaries():
    assert extract_symbols("the doge army") == ["DOGE"]
    assert extract_symbols("nothing to see") == []


def test_extract_chain_keeps_defillama_capitalisation():
    assert extract_chain("tvl on arbitrum") == "Arbitrum"
    assert extract_chain("fees on bsc") == "BSC"
    assert extract_chain("no chain here") is None


def test_coingecko_ids_skip_unknown_symbols():
    assert to_coingecko_ids(["BTC", "NOPE"]) == ["coingecko:bitcoin"]


def test_formatters_handle_bad_input():
    assert fmt_money(1234.5) == "$1,234.50"
    assert fmt_money(None) == "N/A" and fmt_money("abc") == "N/A"
    assert fmt_pct(4.05) == "+4.05%" and fmt_pct(-1) == "-1.00%" and fmt_pct(None) == "N/A"
    assert fmt_num(1234567.4) == "1,234,567" and fmt_num(1.23456, 2) == "1.23"
