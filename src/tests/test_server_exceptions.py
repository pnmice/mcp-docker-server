"""Tests for exception handling and edge cases in server.py."""

import sys
from typing import Any
from unittest.mock import Mock, patch

import pytest


@pytest.mark.unit
class TestServerExceptionHandling:
    """Test exception handling throughout the server."""

    def test_stdout_reconfigure_exception_handling(self) -> None:
        """Test that stdout reconfigure exceptions are handled gracefully."""
        # This tests lines 80-82 in server.py

        # Mock stdout without reconfigure method to trigger the exception path
        mock_stdout = Mock()
        del mock_stdout.reconfigure  # Remove the method to cause AttributeError

        with patch.object(sys, "stdout", mock_stdout):
            with patch.object(sys, "stderr", mock_stdout):
                # This should import the server module and trigger the reconfigure code
                # The exception should be caught and handled gracefully
                try:
                    # Force reimport to trigger the module-level code
                    import importlib

                    import mcp_docker_server.server

                    importlib.reload(mcp_docker_server.server)
                except Exception as e:
                    # Should not raise any exception from reconfigure failure
                    pytest.fail(f"Unexpected exception from stdout reconfigure: {e}")

    def test_stdout_reconfigure_with_exception(self) -> None:
        """Test stdout reconfigure when reconfigure method raises exception."""
        mock_stdout = Mock()
        mock_stdout.reconfigure.side_effect = Exception("Reconfigure failed")
        mock_stderr = Mock()
        mock_stderr.reconfigure.side_effect = Exception("Reconfigure failed")

        with patch.object(sys, "stdout", mock_stdout):
            with patch.object(sys, "stderr", mock_stderr):
                try:
                    import importlib

                    import mcp_docker_server.server

                    importlib.reload(mcp_docker_server.server)
                except Exception as e:
                    pytest.fail(f"Unexpected exception from reconfigure error: {e}")

    def test_logging_handler_flush_enhancement(self) -> None:
        """Test that logging handler flush enhancement doesn't break anything."""
        # This tests the logging setup code that creates enhanced flush functions
        import logging

        # Create a test handler
        handler = logging.StreamHandler()

        # The server module should enhance flush methods
        # Import should complete without errors
        try:
            import mcp_docker_server.server  # noqa: F401
        except Exception as e:
            pytest.fail(f"Server import failed due to logging setup: {e}")

        # Handler should still be functional
        try:
            handler.flush()
        except Exception as e:
            pytest.fail(f"Enhanced flush method failed: {e}")

    @patch("mcp_docker_server.server.logger")
    def test_logging_configuration_robustness(self, mock_logger: Mock) -> None:
        """Test that logging configuration is robust to various environments."""
        # Test that the logging setup doesn't fail in different environments

        # Mock various scenarios that could occur during logging setup
        with patch("logging.StreamHandler") as mock_handler_class:
            mock_handler = Mock()
            mock_handler.level = 0  # Set a valid level for comparison
            mock_handler_class.return_value = mock_handler

            # Test handler without flush method
            del mock_handler.flush

            try:
                import importlib

                import mcp_docker_server.server

                importlib.reload(mcp_docker_server.server)
            except Exception as e:
                pytest.fail(f"Logging setup failed with missing flush: {e}")

    def test_cache_size_limit_boundary(self) -> None:
        """Test cache behavior at the size limit boundary."""
        from mcp_docker_server.server import _cache_image_info

        # This tests the cache eviction logic
        mock_cache: dict[str, dict[str, Any]] = {}
        with patch("mcp_docker_server.server._image_cache", mock_cache):
            with patch("mcp_docker_server.server._CACHE_SIZE_LIMIT", 2):
                # Fill cache to capacity
                _cache_image_info("img1", {"id": "img1"})
                _cache_image_info("img2", {"id": "img2"})

                assert len(mock_cache) == 2

                # This should trigger eviction
                _cache_image_info("img3", {"id": "img3"})

                # Cache should have been partially cleared
                assert len(mock_cache) <= 2

    def test_image_cache_thread_safety(self) -> None:
        """Test that image cache operations are thread-safe."""
        import threading

        from mcp_docker_server.server import _cache_image_info, _get_cached_image_info

        errors = []

        def cache_worker(worker_id: int) -> None:
            try:
                for i in range(10):
                    _cache_image_info(
                        f"img_{worker_id}_{i}", {"id": f"img_{worker_id}_{i}"}
                    )
                    cached = _get_cached_image_info(f"img_{worker_id}_{i}")
                    if cached is None:
                        errors.append(f"Cache miss for img_{worker_id}_{i}")
            except Exception as e:
                errors.append(f"Worker {worker_id} error: {e}")

        threads = []
        for i in range(3):
            thread = threading.Thread(target=cache_worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        assert len(errors) == 0, f"Thread safety errors: {errors}"
