import pytest
from pydantic import ValidationError

from app.config import Settings


def test_configuration_errors_do_not_echo_input_secrets():
    with pytest.raises(ValidationError) as failure:
        Settings(_env_file=None, llm_api_key={"invalid": "synthetic-secret-sentinel"})
    assert "synthetic-secret-sentinel" not in str(failure.value)


@pytest.mark.parametrize(
    "url",
    [
        "http://untrusted.example/v1",
        "https://user:password@example.com/v1",
        "https://example.com/v1?key=secret",
        "file:///tmp/provider",
    ],
)
def test_unsafe_provider_urls_rejected(url):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, llm_base_url=url)
