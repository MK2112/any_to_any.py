
def test_logging_and_progress(any_to_any_instance, caplog):
    with caplog.at_level("INFO"):
        any_to_any_instance.event_logger.info("Test log message")
    assert any("Test log message" in r.getMessage() for r in caplog.records)
