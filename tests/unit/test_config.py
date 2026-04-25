"""Unit tests for config module."""
import pytest
from pydantic import ValidationError

from config import Config


class TestConfig:
    def test_valid_config_loads(self, tmp_path):
        cfg = Config(
            gemini_api_key="AIzaSy_test_key_12345678901234567890",
            database_path=str(tmp_path / "test.db"),
            log_path=str(tmp_path / "agent.log"),
        )
        assert cfg.gemini_api_key.startswith("AIzaSy")
        assert cfg.gemini_model == "gemini-2.5-flash"
        assert cfg.auto_apply_threshold == 85
        assert cfg.semi_auto_threshold == 70

    def test_api_key_now_optional(self):
        cfg = Config(gemini_api_key="")
        assert cfg.gemini_api_key == ""

    def test_semi_threshold_must_be_less_than_auto(self):
        with pytest.raises(ValidationError, match="less than auto_apply_threshold"):
            Config(
                gemini_api_key="AIzaSy_test_key_12345678901234567890",
                auto_apply_threshold=70,
                semi_auto_threshold=85,
            )

    def test_log_level_normalized_to_upper(self):
        cfg = Config(
            gemini_api_key="AIzaSy_test_key_12345678901234567890",
            log_level="debug",
        )
        assert cfg.log_level == "DEBUG"

    def test_invalid_log_level_rejected(self):
        with pytest.raises(ValidationError):
            Config(
                gemini_api_key="AIzaSy_test_key_12345678901234567890",
                log_level="GOSSIP",
            )

    def test_thresholds_out_of_range_rejected(self):
        with pytest.raises(ValidationError):
            Config(
                gemini_api_key="AIzaSy_test_key_12345678901234567890",
                auto_apply_threshold=150,
            )

    def test_search_interval_bounds(self):
        with pytest.raises(ValidationError):
            Config(
                gemini_api_key="AIzaSy_test_key_12345678901234567890",
                search_interval_seconds=10,
            )

    def test_ensure_directories_creates_paths(self, tmp_path):
        db_path = tmp_path / "nested" / "dir" / "jobs.db"
        cfg = Config(
            gemini_api_key="AIzaSy_test_key_12345678901234567890",
            database_path=str(db_path),
            log_path=str(tmp_path / "logs" / "agent.log"),
        )
        cfg.ensure_directories()
        assert db_path.parent.exists()
