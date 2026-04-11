import utils.prog_logger as prog_mod

from utils.prog_logger import ProgLogger

# ProgLogger tests for bars_callback
# without invoking the actual tqdm bars or time delays

class MockTqdm:
    def __init__(self, total=None, unit=None, dynamic_ncols=None, leave=None):
        self.total = total
        self.unit = unit
        self.dynamic_ncols = dynamic_ncols
        self.leave = leave
        self.updated = []
        self.closed = False

    def update(self, delta):
        self.updated.append(delta)

    def close(self):
        self.closed = True


def test_init_without_job_does_not_touch_shared_dict():
    shared = {}
    logger = ProgLogger(job_id=None, shared_progress_dict=shared)
    assert logger.job_id is None
    assert shared == {}


def test_init_with_job_initializes_shared_state():
    shared = {}
    logger = ProgLogger(job_id="job-1", shared_progress_dict=shared)
    assert logger.job_id == "job-1"
    assert shared["job-1"]["status"] == "starting"
    assert shared["job-1"]["progress"] == 0


def test_format_time_handles_none_and_negative():
    logger = ProgLogger()
    assert logger._format_time(None) is None
    assert logger._format_time(-1) is None


def test_format_time_formats_seconds_minutes_hours():
    logger = ProgLogger()
    assert logger._format_time(8) == "8s"
    assert logger._format_time(75) == "1m 15s"
    assert logger._format_time(3661) == "1h 1m 1s"


def test_bars_callback_returns_when_bar_missing(monkeypatch):
    monkeypatch.setattr(prog_mod, "tqdm", MockTqdm)
    logger = ProgLogger()
    logger.bars.clear()
    logger.bars_callback("encode", "index", 1, old_value=0)
    assert logger.tqdm_bar is None


def test_bars_callback_ignores_non_index_updates(monkeypatch):
    monkeypatch.setattr(prog_mod, "tqdm", MockTqdm)
    logger = ProgLogger()
    logger.bars.clear()
    logger.bars["encode"] = {"total": 10}
    logger.bars_callback("encode", "total", 10, old_value=0)
    assert logger.tqdm_bar is None


def test_bars_callback_initializes_tqdm_and_processing_status(monkeypatch):
    monkeypatch.setattr(prog_mod, "tqdm", MockTqdm)
    shared = {}
    logger = ProgLogger(job_id="job-2", shared_progress_dict=shared)
    logger.bars.clear()
    logger.bars["encode"] = {"total": 8}

    times = iter([100.0, 100.0])
    monkeypatch.setattr(prog_mod.time, "time", lambda: next(times))
    logger.bars_callback("encode", "index", 1, old_value=0)

    assert logger.tqdm_bar is not None
    assert logger.tqdm_bar.total == 8
    assert shared["job-2"]["status"] == "processing"
    assert shared["job-2"]["total"] == 8


def test_bars_callback_updates_delta_progress(monkeypatch):
    monkeypatch.setattr(prog_mod, "tqdm", MockTqdm)
    logger = ProgLogger()
    logger.bars.clear()
    logger.bars["encode"] = {"total": 20}

    times = iter([10.0, 10.0, 10.2])
    monkeypatch.setattr(prog_mod.time, "time", lambda: next(times))

    logger.bars_callback("encode", "index", 5, old_value=0)
    logger.bars_callback("encode", "index", 9, old_value=5)

    assert logger.tqdm_bar.updated == [5, 4]


def test_bars_callback_completion_marks_done(monkeypatch):
    monkeypatch.setattr(prog_mod, "tqdm", MockTqdm)
    shared = {}
    logger = ProgLogger(job_id="job-3", shared_progress_dict=shared)
    logger.bars.clear()
    logger.bars["encode"] = {"total": 10}

    times = iter([200.0, 200.0, 201.0, 202.0])
    monkeypatch.setattr(prog_mod.time, "time", lambda: next(times))

    logger.bars_callback("encode", "index", 2, old_value=0)
    logger.bars_callback("encode", "index", 10, old_value=2)

    assert logger.tqdm_bar.closed is True
    assert shared["job-3"]["status"] == "done"
    assert shared["job-3"]["progress_percent"] == 100
    assert shared["job-3"]["eta_seconds"] == 0


def test_bars_callback_zero_total_avoids_division_by_zero(monkeypatch):
    monkeypatch.setattr(prog_mod, "tqdm", MockTqdm)
    logger = ProgLogger()
    logger.bars.clear()
    logger.bars["encode"] = {"total": 0}

    times = iter([50.0, 50.0])
    monkeypatch.setattr(prog_mod.time, "time", lambda: next(times))

    logger.bars_callback("encode", "index", 0, old_value=0)

    assert logger.tqdm_bar is not None
    assert logger.tqdm_bar.total == 0


def test_set_error_sets_error_state():
    shared = {}
    logger = ProgLogger(job_id="job-4", shared_progress_dict=shared)
    logger.set_error("conversion failed")
    assert shared["job-4"]["status"] == "error"
    assert shared["job-4"]["error"] == "conversion failed"


def test_set_error_without_job_does_nothing():
    logger = ProgLogger(job_id=None, shared_progress_dict={})
    logger.set_error("irrelevant") # Must not raise
