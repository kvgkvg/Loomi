from core_service.poller import GitPoller


class FakeRepo:
    def __init__(self):
        self.head = "abc"
        self.capture_calls = []
        self.process_calls = []
        self.results = [{"embedded": True, "asset_id": "asset-1", "version_id": "v1"}]

    def resolve_head(self):
        return self.head

    def capture(self, sha):
        self.capture_calls.append(sha)
        return {
            "raw_event_id": f"raw-{sha}",
            "title": "Prompt update",
            "source_tool": "git",
        }

    def process(self, raw_event_id):
        self.process_calls.append(raw_event_id)
        return self.results.pop(0)


def make_poller(fake_repo, isolated_runtime, published=None, **kwargs):
    published = published if published is not None else []
    return GitPoller(
        repository=isolated_runtime,
        resolve_head=fake_repo.resolve_head,
        capture=fake_repo.capture,
        process=fake_repo.process,
        publish=published.append,
        **kwargs,
    )


def test_unchanged_head_is_not_recaptured(isolated_runtime):
    repo = FakeRepo()
    poller = make_poller(repo, isolated_runtime)

    poller.poll_once()
    poller.poll_once()

    assert repo.capture_calls == ["abc"]
    assert repo.process_calls == ["raw-abc"]


def test_incomplete_processing_retries_same_raw_event(isolated_runtime):
    repo = FakeRepo()
    repo.results = [
        {"embedded": False, "error": "provider unavailable"},
        {"embedded": True, "asset_id": "asset-1", "version_id": "v1"},
    ]
    published = []
    poller = make_poller(repo, isolated_runtime, published)

    poller.poll_once()
    assert poller.retry_delay == 3
    poller.poll_once()

    assert repo.capture_calls == ["abc"]
    assert repo.process_calls == ["raw-abc", "raw-abc"]
    assert [event["type"] for event in published] == [
        "capture_started",
        "capture_retrying",
        "memory_ready",
    ]


def test_processed_sha_survives_restart(isolated_runtime):
    repo = FakeRepo()
    make_poller(repo, isolated_runtime).poll_once()

    make_poller(repo, isolated_runtime).poll_once()

    assert repo.capture_calls == ["abc"]


def test_backoff_is_bounded_and_resets_after_success(isolated_runtime):
    repo = FakeRepo()
    repo.results = [
        {"embedded": False},
        {"embedded": False},
        {"embedded": False},
        {"embedded": True, "asset_id": "asset-1", "version_id": "v1"},
    ]
    poller = make_poller(repo, isolated_runtime, max_backoff=10)

    poller.poll_once()
    assert poller.retry_delay == 3
    poller.poll_once()
    assert poller.retry_delay == 6
    poller.poll_once()
    assert poller.retry_delay == 10
    poller.poll_once()
    assert poller.retry_delay == 0


def test_new_head_does_not_replace_pending_retry(isolated_runtime):
    repo = FakeRepo()
    repo.results = [
        {"embedded": False},
        {"embedded": True, "asset_id": "asset-1", "version_id": "v1"},
        {"embedded": True, "asset_id": "asset-1", "version_id": "v2"},
    ]
    poller = make_poller(repo, isolated_runtime)

    poller.poll_once()
    repo.head = "def"
    poller.poll_once()
    poller.poll_once()

    assert repo.capture_calls == ["abc", "def"]
    assert repo.process_calls == ["raw-abc", "raw-abc", "raw-def"]


def test_run_stops_without_an_extra_poll(isolated_runtime):
    repo = FakeRepo()
    poller = make_poller(repo, isolated_runtime)
    calls = []
    poller.poll_once = lambda: calls.append("poll")

    poller.start()
    poller.stop()
    assert calls == ["poll"]
