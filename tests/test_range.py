"""Tests for the RSSI → distance conversion in src/range.py."""
import pytest

from src.range import METRES_TO_FEET, N, TX_POWER, rssi_to_feet


def test_rssi_at_tx_power_is_one_metre():
    """At RSSI == TX_POWER the path-loss exponent yields exactly 1 m."""
    result = rssi_to_feet(TX_POWER)
    assert abs(result - METRES_TO_FEET) < 1e-9


def test_stronger_signal_is_closer():
    """A stronger signal (less-negative RSSI) should resolve to a shorter distance."""
    assert rssi_to_feet(-40) < rssi_to_feet(TX_POWER)


def test_weaker_signal_is_farther():
    """A weaker signal (more-negative RSSI) should resolve to a longer distance."""
    assert rssi_to_feet(-80) > rssi_to_feet(TX_POWER)


def test_returns_float():
    assert isinstance(rssi_to_feet(-70), float)


def test_distance_always_positive():
    for rssi in (-100, -80, -59, -40, -20):
        assert rssi_to_feet(rssi) > 0


def test_known_calculation():
    """Cross-check against the formula: d_m = 10^((TX - rssi)/(10*N)) * METRES_TO_FEET."""
    rssi = -70
    d_m = 10 ** ((TX_POWER - rssi) / (10 * N))
    expected = d_m * METRES_TO_FEET
    assert abs(rssi_to_feet(rssi) - expected) < 1e-9
