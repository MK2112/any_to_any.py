import pytest
from tests.test_fixtures import converter_instance

def test_logging_and_progress(converter_instance, caplog):
    with caplog.at_level("INFO"):
        converter_instance.event_logger.info("Test log message")
    assert any("Test log message" in r.getMessage() for r in caplog.records)
