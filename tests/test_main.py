"""Tests for pure functions in src/main.py."""
import pytest

from src.main import ELK_TURN_OFF, ELK_TURN_ON, elk_rgb


# ── elk_rgb ───────────────────────────────────────────────────────────────────

def test_elk_rgb_encodes_colour():
    assert elk_rgb(255, 128, 0) == bytes([0x7E, 0x00, 0x05, 0x03, 255, 128, 0, 0x00, 0xEF])


def test_elk_rgb_black():
    assert elk_rgb(0, 0, 0) == bytes([0x7E, 0x00, 0x05, 0x03, 0, 0, 0, 0x00, 0xEF])


def test_elk_rgb_white():
    assert elk_rgb(255, 255, 255) == bytes([0x7E, 0x00, 0x05, 0x03, 255, 255, 255, 0x00, 0xEF])


def test_elk_rgb_length():
    assert len(elk_rgb(100, 200, 50)) == 9


def test_elk_rgb_header_and_footer_unchanged():
    """Protocol header (byte 0) and footer (byte 8) must always be 0x7E / 0xEF."""
    payload = elk_rgb(10, 20, 30)
    assert payload[0] == 0x7E
    assert payload[8] == 0xEF


def test_elk_rgb_colour_bytes_at_correct_positions():
    r, g, b = 11, 22, 33
    payload = elk_rgb(r, g, b)
    assert payload[4] == r
    assert payload[5] == g
    assert payload[6] == b


# ── ELK_TURN_ON / ELK_TURN_OFF ───────────────────────────────────────────────

def test_elk_turn_on_bytes():
    assert ELK_TURN_ON == bytes([0x7E, 0x00, 0x04, 0xF0, 0x00, 0x00, 0x00, 0x00, 0xEF])


def test_elk_turn_off_bytes():
    assert ELK_TURN_OFF == bytes([0x7E, 0x00, 0x04, 0x00, 0x00, 0x00, 0x00, 0xFF, 0xEF])


def test_elk_turn_on_length():
    assert len(ELK_TURN_ON) == 9


def test_elk_turn_off_length():
    assert len(ELK_TURN_OFF) == 9
