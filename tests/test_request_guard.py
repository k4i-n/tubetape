from email.message import Message

import pytest

from tubetape.server import is_own_request


def headers(**values: str) -> Message:
    message = Message()
    for key, value in values.items():
        message[key.replace("_", "-")] = value
    return message


def test_accepts_the_app_page() -> None:
    own = headers(Host="127.0.0.1:8765", Origin="http://127.0.0.1:8765", Sec_Fetch_Site="same-origin")
    assert is_own_request(own, 8765, post=True)
    assert is_own_request(headers(Host="localhost:8765"), 8765, post=False)


@pytest.mark.parametrize(
    "request_headers",
    [
        headers(Host="evil.example:8765", Origin="http://evil.example:8765"),
        headers(Host="127.0.0.1:8765", Origin="https://evil.example"),
        headers(Host="127.0.0.1:8765"),
        headers(Host="127.0.0.1:8765", Origin="http://127.0.0.1:8765", Sec_Fetch_Site="cross-site"),
    ],
)
def test_rejects_other_sites(request_headers: Message) -> None:
    assert not is_own_request(request_headers, 8765, post=True)
