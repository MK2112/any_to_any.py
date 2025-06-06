import pytest
from tests.test_fixtures import controller_instance


def test_logging_and_progress(controller_instance, caplog):
    with caplog.at_level("INFO"):
        controller_instance.event_logger.info("Test log message")
    assert any("Test log message" in r.getMessage() for r in caplog.records)
