from kompressor.proxy import healthz, prepare_messages_request


def test_healthz() -> None:
    assert healthz() == {"status": "ok"}


def test_prepare_request_dry_run() -> None:
    req = {"messages": [{"role": "user", "content": '[{"a":"b"},{"a":"c"}]'}]}
    prepared = prepare_messages_request(req)
    assert prepared["_kompressor"]["dry_run"] is True
    assert prepared["_kompressor"]["forwarded"] is False
