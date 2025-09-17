"""
Tests for server settings.
"""

import os
from unittest.mock import patch

import pytest

from mcp_docker_server.settings import ServerSettings


@pytest.mark.unit
class TestServerSettings:
    """Test server settings configuration."""

    def test_default_settings(self) -> None:
        """Test default settings values."""
        settings = ServerSettings()

        assert settings.docker_host is None
        assert settings.docker_tls_verify is False
        assert settings.docker_cert_path is None
        assert settings.docker_api_version is None

    def test_settings_from_env_vars(self) -> None:
        """Test settings loaded from environment variables."""
        env_vars = {
            "DOCKER_HOST": "tcp://localhost:2376",
            "DOCKER_TLS_VERIFY": "1",
            "DOCKER_CERT_PATH": "/certs",
            "DOCKER_API_VERSION": "1.41",
        }

        with patch.dict(os.environ, env_vars):
            settings = ServerSettings()

            assert settings.docker_host == "tcp://localhost:2376"
            assert settings.docker_tls_verify is True
            assert settings.docker_cert_path == "/certs"
            assert settings.docker_api_version == "1.41"

    def test_settings_explicit_values(self) -> None:
        """Test settings with explicitly provided values."""
        settings = ServerSettings(
            docker_host="tcp://example.com:2376",
            docker_tls_verify=True,
            docker_cert_path="/custom/certs",
            docker_api_version="1.40",
        )

        assert settings.docker_host == "tcp://example.com:2376"
        assert settings.docker_tls_verify is True
        assert settings.docker_cert_path == "/custom/certs"
        assert settings.docker_api_version == "1.40"

    def test_settings_override_env_with_explicit(self) -> None:
        """Test that explicit values override environment variables."""
        env_vars = {"DOCKER_HOST": "tcp://env-host:2376", "DOCKER_TLS_VERIFY": "1"}

        with patch.dict(os.environ, env_vars):
            settings = ServerSettings(
                docker_host="tcp://explicit-host:2376", docker_tls_verify=False
            )

            assert settings.docker_host == "tcp://explicit-host:2376"
            assert settings.docker_tls_verify is False

    def test_docker_tls_verify_string_values(self) -> None:
        """Test DOCKER_TLS_VERIFY accepts various string values."""
        test_cases = [
            ("1", True),
            ("true", True),
            ("True", True),
            ("TRUE", True),
            ("yes", True),
            ("0", False),
            ("false", False),
            ("False", False),
            ("FALSE", False),
            ("no", False),
            ("", False),
        ]

        for env_value, expected in test_cases:
            with patch.dict(os.environ, {"DOCKER_TLS_VERIFY": env_value}):
                settings = ServerSettings()
                assert (
                    settings.docker_tls_verify is expected
                ), f"Failed for {env_value!r}"

    def test_settings_model_validation(self) -> None:
        """Test that settings model validates correctly."""
        # Should not raise any validation errors
        settings = ServerSettings(
            docker_host="unix:///var/run/docker.sock", docker_api_version="auto"
        )

        assert settings.docker_host == "unix:///var/run/docker.sock"
        assert settings.docker_api_version == "auto"

    @patch.dict(os.environ, {}, clear=True)
    def test_settings_no_env_vars(self) -> None:
        """Test settings when no environment variables are set."""
        settings = ServerSettings()

        assert settings.docker_host is None
        assert settings.docker_tls_verify is False
        assert settings.docker_cert_path is None
        assert settings.docker_api_version is None
