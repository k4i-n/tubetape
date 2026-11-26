import argparse

import pytest

from tubetape import workers


def test_workers_accepts_1_to_32() -> None:
    assert workers("1") == 1
    assert workers("32") == 32


@pytest.mark.parametrize("text", ["0", "33", "-1"])
def test_workers_rejects_out_of_range(text: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        workers(text)
