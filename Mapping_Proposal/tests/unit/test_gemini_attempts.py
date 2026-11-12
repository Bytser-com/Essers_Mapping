"""Verify the Gemini request loop really supports the configured 20 attempts."""

from types import SimpleNamespace

from scripts import readprompt


class FakeServerError(Exception):
    code = 503


class Client:
    def __init__(self):
        self.attempts = 0
        self.closed = False
        self.models = self

    def generate_content(self, **kwargs):
        self.attempts += 1
        if self.attempts < 20:
            raise FakeServerError('Overloaded')
        return SimpleNamespace(usage_metadata=None, text='{"mappings": []}')

    def close(self):
        self.closed = True


def test_twenty_attempts_with_one_success(monkeypatch, caplog):
    client = Client()
    monkeypatch.setattr(readprompt, 'genai', SimpleNamespace(Client=lambda **kwargs: client))
    monkeypatch.setattr(readprompt, 'errors', SimpleNamespace(ServerError=FakeServerError, ClientError=type('FakeClientError', (Exception,), {})))
    monkeypatch.setattr(readprompt, 'types', SimpleNamespace(
        HttpOptions=lambda **kwargs: None, HttpRetryOptions=lambda **kwargs: None,
        GenerateContentConfig=lambda **kwargs: None,
    ))
    monkeypatch.setattr(readprompt, 'load_settings', lambda: SimpleNamespace(
        gemini_api_key='test', gemini_model='test-model', gemini_timeout_ms=1000,
    ))
    monkeypatch.setattr(readprompt, 'gemini_max_attempts', lambda: 20)
    monkeypatch.setattr(readprompt.time, 'sleep', lambda delay: None)
    monkeypatch.setattr(readprompt.random, 'uniform', lambda a, b: 0)
    events = []
    assert readprompt.run_gemini([], [], on_event=events.append) == []
    assert client.attempts == 20
    assert client.closed
    assert sum(e['type'] == 'attempt' for e in events) == 20
    assert sum(e['type'] == 'retry' for e in events) == 19


def test_no_retry_on_daily_quota(monkeypatch):
    # Classification is independently tested by the retry-watcher tests.
    from scripts.errors import QuotaExceededError
    from services.proposal_runner import is_retryable_gemini_error
    assert not is_retryable_gemini_error(QuotaExceededError('daily quota exceeded', code=429))
