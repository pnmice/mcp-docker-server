"""Tests for the main __init__.py module functionality."""

import os
from pathlib import Path
from unittest.mock import Mock, mock_open, patch

from mcp_docker_server import (
    _ensure_ssh_host_key_trusted,
    create_docker_client,
    main,
    resolve_ssh_config,
)


class TestSSHConfigResolution:
    """Test SSH config resolution functionality."""

    def test_resolve_ssh_config_non_ssh_url(self) -> None:
        """Test that non-SSH URLs are returned unchanged."""
        url = "tcp://localhost:2376"
        assert resolve_ssh_config(url) == url

    def test_resolve_ssh_config_empty_url(self) -> None:
        """Test that empty URLs are returned unchanged."""
        assert resolve_ssh_config("") == ""

    def test_resolve_ssh_config_with_user(self) -> None:
        """Test that SSH URLs with user@host are returned unchanged."""
        url = "ssh://user@hostname"
        assert resolve_ssh_config(url) == url

    @patch("pathlib.Path.home")
    def test_resolve_ssh_config_no_ssh_config_file(self, mock_home: Mock) -> None:
        """Test behavior when SSH config file doesn't exist."""
        mock_home.return_value = Path("/nonexistent")
        url = "ssh://myhost"
        assert resolve_ssh_config(url) == url

    @patch("pathlib.Path.home")
    @patch(
        "builtins.open",
        new_callable=mock_open,
        read_data="Host myhost\n  HostName real.example.com\n  User myuser\n  Port 2222\n",
    )
    def test_resolve_ssh_config_with_config(
        self, mock_file: Mock, mock_home: Mock
    ) -> None:
        """Test SSH config resolution with actual config."""
        # Mock the home directory and config file existence
        home_path = Path("/home/user")
        mock_home.return_value = home_path

        # Mock the ssh config file exists
        with patch.object(Path, "exists", return_value=True):
            url = "ssh://myhost"
            result = resolve_ssh_config(url)
            assert result == "ssh://myuser@real.example.com:2222"

    @patch("pathlib.Path.home")
    @patch("builtins.open", side_effect=Exception("File error"))
    def test_resolve_ssh_config_file_error(
        self, mock_file: Mock, mock_home: Mock
    ) -> None:
        """Test that file errors are handled gracefully."""
        mock_home.return_value = Path("/home/user")
        url = "ssh://myhost"
        assert resolve_ssh_config(url) == url


class TestSSHHostKeyTrust:
    """Test SSH host key trust functionality."""

    @patch("subprocess.run")
    @patch("pathlib.Path.home")
    def test_ensure_ssh_host_key_trusted_success(
        self, mock_home: Mock, mock_subprocess: Mock
    ) -> None:
        """Test successful host key addition."""
        mock_home.return_value = Path("/home/user")
        mock_subprocess.return_value = Mock(
            returncode=0, stdout="ssh-rsa AAAAB3... hostname\n"
        )

        # Test that the function doesn't crash and calls subprocess
        _ensure_ssh_host_key_trusted("ssh://example.com")

        mock_subprocess.assert_called_once()

    @patch("subprocess.run")
    def test_ensure_ssh_host_key_trusted_invalid_url(
        self, mock_subprocess: Mock
    ) -> None:
        """Test behavior with invalid URL."""
        _ensure_ssh_host_key_trusted("invalid://url")
        # The function should still try to call ssh-keyscan since 'url' is a valid hostname
        # but should handle the error gracefully
        mock_subprocess.assert_called_once()

    @patch("subprocess.run", side_effect=Exception("Command failed"))
    def test_ensure_ssh_host_key_trusted_exception(self, mock_subprocess: Mock) -> None:
        """Test that exceptions are handled gracefully."""
        # Should not raise an exception
        _ensure_ssh_host_key_trusted("ssh://example.com")


class TestDockerClientCreation:
    """Test Docker client creation functionality."""

    @patch("docker.from_env")
    @patch("mcp_docker_server.resolve_ssh_config")
    def test_create_docker_client_no_host(
        self, mock_resolve: Mock, mock_docker: Mock
    ) -> None:
        """Test Docker client creation without DOCKER_HOST."""
        mock_resolve.return_value = ""
        mock_docker.return_value = Mock()

        with patch.dict(os.environ, {}, clear=True):
            create_docker_client()

        mock_resolve.assert_called_once_with("")
        mock_docker.assert_called_once()

    @patch("docker.from_env")
    @patch("mcp_docker_server.resolve_ssh_config")
    @patch("mcp_docker_server._ensure_ssh_host_key_trusted")
    def test_create_docker_client_ssh_host(
        self, mock_trust: Mock, mock_resolve: Mock, mock_docker: Mock
    ) -> None:
        """Test Docker client creation with SSH host."""
        mock_resolve.return_value = "ssh://user@example.com"
        mock_docker.return_value = Mock()

        with patch.dict(os.environ, {"DOCKER_HOST": "ssh://myhost"}, clear=True):
            create_docker_client()
            # Check the environment variable while still in the patched context
            assert os.environ.get("DOCKER_HOST") == "ssh://user@example.com"

        mock_resolve.assert_called_once_with("ssh://myhost")
        mock_trust.assert_called_once_with("ssh://user@example.com")
        mock_docker.assert_called_once()

    @patch("docker.from_env")
    @patch("mcp_docker_server.resolve_ssh_config")
    @patch(
        "mcp_docker_server._ensure_ssh_host_key_trusted",
        side_effect=Exception("Trust failed"),
    )
    def test_create_docker_client_trust_failure(
        self, mock_trust: Mock, mock_resolve: Mock, mock_docker: Mock
    ) -> None:
        """Test that trust failures don't prevent client creation."""
        mock_resolve.return_value = "ssh://user@example.com"
        mock_docker.return_value = Mock()

        with patch.dict(os.environ, {"DOCKER_HOST": "ssh://myhost"}, clear=True):
            create_docker_client()

        mock_docker.assert_called_once()


class TestMainEntry:
    """Test main entry point."""

    @patch("mcp_docker_server.run_stdio")
    @patch("mcp_docker_server.create_docker_client")
    @patch("mcp_docker_server.ServerSettings")
    @patch("asyncio.run")
    def test_main_entry_point(
        self, mock_asyncio: Mock, mock_settings: Mock, mock_client: Mock, mock_run: Mock
    ) -> None:
        """Test that main() calls all required functions."""
        mock_settings.return_value = Mock()
        mock_client.return_value = Mock()

        main()

        mock_settings.assert_called_once()
        mock_client.assert_called_once()
        mock_asyncio.assert_called_once()
