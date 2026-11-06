from __future__ import annotations

import pytest

from task3.gateway.redactor import MAX_PATTERN_LEN, REDACTION, TAIL_LENGTH, StreamRedactor


PII_CASES = (
    ("email", "ada.lovelace@example.com"),
    ("ssn", "123-45-6789"),
    ("card", "4111-1111-1111-1111"),
    ("card", "4111 1111 1111 1111"),
    ("card", "4111111111111111"),
)


def run_chunks(*chunks: str) -> tuple[str, StreamRedactor]:
    redactor = StreamRedactor()
    output = "".join(redactor.feed(chunk) for chunk in chunks) + redactor.flush()
    return output, redactor


@pytest.mark.parametrize(("kind", "value"), PII_CASES)
def test_each_pattern_is_redacted_when_fed_whole(kind: str, value: str) -> None:
    output, redactor = run_chunks(f"before {value} after")
    assert output == f"before {REDACTION} after"
    assert redactor.redaction_counts[kind] == 1


@pytest.mark.parametrize(("kind", "value"), PII_CASES)
def test_one_character_at_a_time_equals_one_call(kind: str, value: str) -> None:
    text = f"prefix:{value}:suffix"
    whole, _ = run_chunks(text)
    characterwise, redactor = run_chunks(*text)
    assert characterwise == whole
    assert redactor.redaction_counts[kind] == 1


@pytest.mark.parametrize(("kind", "value"), PII_CASES)
def test_every_two_chunk_split_equals_one_call(kind: str, value: str) -> None:
    # Make the input longer than the carry window so this exercises incremental
    # emission, not merely two writes followed by a final flush.
    text = f"{'x' * (MAX_PATTERN_LEN + 5)}:{value}:{'y' * (MAX_PATTERN_LEN + 5)}"
    expected, _ = run_chunks(text)
    for offset in range(len(text) + 1):
        actual, redactor = run_chunks(text[:offset], text[offset:])
        assert actual == expected, f"failed at offset {offset} for {kind}"
        assert redactor.redaction_counts[kind] == 1


def test_card_one_character_at_a_time_has_exact_whole_output() -> None:
    value = "4111-1111-1111-1111"
    whole, _ = run_chunks(value)
    characterwise, _ = run_chunks(*value)
    assert whole == characterwise == REDACTION


@pytest.mark.parametrize("digit_count", range(13, 20))
@pytest.mark.parametrize("separator", ("", "-", " "))
def test_every_supported_card_length_and_separator(digit_count: int, separator: str) -> None:
    card = separator.join("4" * digit_count)
    output, redactor = run_chunks(*card)
    assert output == REDACTION
    assert redactor.redaction_counts["card"] == 1


def test_pii_at_start_and_at_end_is_caught_by_flush() -> None:
    start, _ = run_chunks("123-45-6789 then clean")
    redactor = StreamRedactor()
    before_flush = redactor.feed("clean then ada@example.com")
    end = before_flush + redactor.flush()
    assert start == f"{REDACTION} then clean"
    assert before_flush == ""
    assert end == f"clean then {REDACTION}"


def test_adjacent_pii_items_are_both_redacted() -> None:
    output, redactor = run_chunks("123-45-6789ada@example.com")
    assert output == REDACTION * 2
    assert redactor.redaction_counts == {"ssn": 1, "card": 0, "email": 1}


@pytest.mark.parametrize(
    "clean",
    (
        "No private data appears in this document.",
        "123456789012",  # Too short for a card.
        "12345678901234567890",  # Too long for a card.
        "123-45-678",  # Incomplete SSN.
        "name@example",  # Incomplete email.
        "The literal marker [REDACTED] remains unchanged.",
    ),
)
def test_clean_or_near_match_text_is_byte_identical(clean: str) -> None:
    output, redactor = run_chunks(*clean)
    assert output == clean
    assert redactor.redaction_counts == {"ssn": 0, "card": 0, "email": 0}


def test_mixed_patterns_and_counts() -> None:
    text = "Email a@example.com, SSN 123-45-6789, card 4111111111111111."
    output, redactor = run_chunks(*text)
    assert output == f"Email {REDACTION}, SSN {REDACTION}, card {REDACTION}."
    assert redactor.redaction_counts == {"ssn": 1, "card": 1, "email": 1}


def test_memory_is_bounded_and_clean_prefix_is_emitted() -> None:
    redactor = StreamRedactor()
    emitted = redactor.feed("x" * (MAX_PATTERN_LEN * 4))
    assert emitted
    assert redactor.buffered_characters == TAIL_LENGTH


def test_long_clean_document_is_identical_during_incremental_emission() -> None:
    clean = ("A clean sentence without private values. " * 100).rstrip()
    output, redactor = run_chunks(*(clean[index : index + 7] for index in range(0, len(clean), 7)))
    assert output == clean
    assert redactor.buffered_characters == 0
    assert redactor.redaction_counts == {"ssn": 0, "card": 0, "email": 0}


def test_flush_clears_buffer_and_instance_can_be_reused() -> None:
    redactor = StreamRedactor()
    redactor.feed("a@example.com")
    assert redactor.flush() == REDACTION
    assert redactor.buffered_characters == 0
    redactor.feed("123-45-6789")
    assert redactor.flush() == REDACTION


def test_feed_rejects_non_string_input() -> None:
    redactor = StreamRedactor()
    with pytest.raises(TypeError, match="expects str"):
        redactor.feed(b"text")  # type: ignore[arg-type]
