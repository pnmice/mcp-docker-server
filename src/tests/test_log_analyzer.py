"""
Unit tests for log analysis functionality.
"""

from unittest.mock import Mock

import pytest

from mcp_docker_server.log_analyzer import LogAnalyzer
from mcp_docker_server.server import (
    _handle_analyze_container_logs,
    _handle_container_tools,
)


@pytest.mark.unit
class TestLogAnalyzer:
    """Test the LogAnalyzer class."""

    def test_init(self) -> None:
        """Test LogAnalyzer initialization."""
        analyzer = LogAnalyzer()

        assert len(analyzer.noise_patterns) > 0
        assert len(analyzer.important_levels) > 0
        assert len(analyzer.important_keywords) > 0
        assert isinstance(analyzer.pattern_cache, dict)
        assert isinstance(analyzer.seen_patterns, set)

    def test_extract_log_template(self) -> None:
        """Test log template extraction with variable replacement."""
        analyzer = LogAnalyzer()

        # Test timestamp replacement
        log_with_timestamp = "[2025-09-18T20:22:12Z INFO] Test message"
        template = analyzer.extract_log_template(log_with_timestamp)
        assert "<TIMESTAMP>" in template
        assert "2025-09-18T20:22:12Z" not in template

        # Test number replacement
        log_with_numbers = "Process 12345 using 25 GB memory"
        template = analyzer.extract_log_template(log_with_numbers)
        assert "Process <NUM> using <NUM> GB memory" == template

        # Test IP address replacement
        log_with_ip = "Connecting to 192.168.1.1:8080"
        template = analyzer.extract_log_template(log_with_ip)
        assert "Connecting to <IP>:<NUM>" == template

        # Test phone number replacement
        log_with_phone = "User phone: +79154133786"
        template = analyzer.extract_log_template(log_with_phone)
        assert "User phone: <PHONE>" == template

        # Test hex ID replacement
        log_with_hex = "Transaction: 9560e24c267ad3f2b966e4ebae94cc9f620bd8862b4d1ec0c0eedf511973371e"
        template = analyzer.extract_log_template(log_with_hex)
        assert "Transaction: <ID>" == template

    def test_is_noise(self) -> None:
        """Test noise pattern detection."""
        analyzer = LogAnalyzer()

        # Should detect HTTP debug noise
        noise_logs = [
            "DEBUG hyper::client::pool] pooling idle connection",
            "DEBUG hyper::proto::h1::io] parsed 9 headers",
            "DEBUG hyper::proto::h1::conn] incoming body is content-length (23 bytes)",
            "flushed 201 bytes",
        ]

        for log in noise_logs:
            assert analyzer.is_noise(log), f"Should detect noise: {log}"

        # Should not detect important logs as noise
        important_logs = [
            "ERROR Failed to process request",
            "INFO Starting application",
            "WARN Connection timeout",
        ]

        for log in important_logs:
            assert not analyzer.is_noise(log), f"Should not detect as noise: {log}"

    def test_is_important(self) -> None:
        """Test important log detection."""
        analyzer = LogAnalyzer()

        # Should detect error levels
        error_logs = [
            "ERROR Something went wrong",
            "WARN Connection timeout",
            "FATAL System crash",
            "PANIC Memory corruption",
        ]

        for log in error_logs:
            assert analyzer.is_important(log), f"Should detect as important: {log}"

        # Should detect important keywords
        keyword_logs = [
            "Failed to connect to database",
            "Payment processing error",
            "Subscription renewal failed",
            "User authentication timeout",
        ]

        for log in keyword_logs:
            assert analyzer.is_important(log), f"Should detect as important: {log}"

        # Should not detect debug logs as important
        debug_logs = [
            "DEBUG Processing request",
            "INFO Normal operation",
            "Regular log message",
        ]

        for log in debug_logs:
            assert not analyzer.is_important(
                log
            ), f"Should not detect as important: {log}"

    def test_analyze_logs_empty(self) -> None:
        """Test log analysis with empty input."""
        analyzer = LogAnalyzer()
        results = analyzer.analyze_logs([])

        assert results["noise_filtered"] == 0
        assert len(results["important_events"]) == 0
        assert len(results["errors"]) == 0
        assert len(results["warnings"]) == 0
        assert len(results["business_events"]) == 0

    def test_analyze_logs_with_noise(self) -> None:
        """Test log analysis with noise filtering."""
        analyzer = LogAnalyzer()

        log_lines = [
            "DEBUG hyper::client::pool] pooling idle connection",
            "DEBUG hyper::proto::h1::io] parsed 9 headers",
            "ERROR Failed to process payment",
            "WARN Connection timeout",
            "INFO Subscription renewed for user 123",
            "DEBUG hyper::proto::h1::conn] incoming body completed",
        ]

        results = analyzer.analyze_logs(log_lines)

        assert results["noise_filtered"] == 3  # 3 debug hyper logs
        assert len(results["errors"]) == 1
        assert len(results["warnings"]) == 1
        assert len(results["important_events"]) == 3  # ERROR, WARN, subscription
        assert len(results["business_events"]) == 2  # payment and subscription

    def test_analyze_logs_business_events(self) -> None:
        """Test business event detection."""
        analyzer = LogAnalyzer()

        log_lines = [
            "INFO Processing payment for user 123",
            "INFO User subscription activated",
            "DEBUG Normal debug message",
            "INFO Renewal check completed",
            "ERROR Payment failed for subscription 456",
        ]

        results = analyzer.analyze_logs(log_lines)

        # Should detect business events based on keywords
        business_events = results["business_events"]
        assert len(business_events) == 4  # All except debug message

        # Check specific business event content
        payment_events = [e for e in business_events if "payment" in e.lower()]
        subscription_events = [
            e for e in business_events if "subscription" in e.lower()
        ]

        assert len(payment_events) == 2
        assert len(subscription_events) == 2

    def test_deduplicate_similar_logs(self) -> None:
        """Test log deduplication based on templates."""
        analyzer = LogAnalyzer()

        log_lines = [
            "Processing request 123",
            "Processing request 456",
            "Processing request 789",
            "Unique log message",
            "Another unique message",
        ]

        result = analyzer.deduplicate_similar_logs(log_lines)

        # Should group similar "Processing request" logs
        assert len(result) == 3  # 1 grouped + 2 unique

        # Find the grouped entry
        grouped_entry = None
        for entry, count in result:
            if "Processing request" in entry and "(x3)" in entry:
                grouped_entry = (entry, count)
                break

        assert grouped_entry is not None
        assert grouped_entry[1] == 3

    def test_format_analysis_summary(self) -> None:
        """Test analysis result formatting."""
        analyzer = LogAnalyzer()

        # Mock analysis results
        results = {
            "noise_filtered": 5,
            "important_events": ["ERROR Test error", "WARN Test warning"],
            "errors": ["ERROR Test error"],
            "warnings": ["WARN Test warning"],
            "business_events": ["Payment processed", "User subscription activated"],
            "patterns": analyzer.analyze_logs(["Test log 1", "Test log 2"])["patterns"],
            "dynamic_noise_patterns": ["Template <NUM>", "Another pattern"],
            "frequency_analysis": {"total_unique_patterns": 10},
        }

        formatted = analyzer.format_analysis_summary(results)

        # Check structure
        assert "summary" in formatted
        assert "errors" in formatted
        assert "warnings" in formatted
        assert "business_events" in formatted
        assert "pattern_analysis" in formatted
        assert "frequency_analysis" in formatted
        assert "noise_detection" in formatted

        # Check summary values
        summary = formatted["summary"]
        assert summary["noise_patterns_filtered"] == 5
        assert summary["important_events_found"] == 2
        assert summary["errors_found"] == 1
        assert summary["warnings_found"] == 1
        assert summary["business_events_found"] == 2
        assert summary["dynamic_noise_patterns_detected"] == 2

    def test_frequency_based_noise_detection(self) -> None:
        """Test frequency-based noise detection."""
        analyzer = LogAnalyzer(noise_threshold=0.5, frequency_threshold=3)

        # Create logs with repetitive patterns
        log_lines = [
            "Connection established to server",
            "Connection established to server",
            "Connection established to server",
            "Connection established to server",
            "ERROR Critical failure occurred",
            "INFO Process completed successfully",
        ]

        noise_patterns = analyzer.detect_frequency_based_noise(log_lines)

        # Should detect the repetitive connection pattern
        assert len(noise_patterns) > 0
        # Should contain normalized template
        connection_template = "Connection established to server"
        assert connection_template in noise_patterns

    def test_enhanced_noise_patterns(self) -> None:
        """Test enhanced noise pattern detection."""
        analyzer = LogAnalyzer()

        # Test various new noise patterns
        noise_logs = [
            "GET /health HTTP/1.1",
            "GET /healthz?check=true HTTP/1.1",
            "User-Agent: ELB-HealthChecker/2.0",
            "GET /assets/main.css HTTP/1.1",
            "GET /static/js/app.js HTTP/1.1",
            "DEBUG Connection pool status",
            "TRACE Method entry point",
            "Connection from 127.0.0.1:8080",
            "Request from 192.168.1.100",
            "Heartbeat signal received",
            "Cache refresh completed",
            "GET /metrics HTTP/1.1",
            "Prometheus scrape endpoint",
        ]

        for log in noise_logs:
            assert analyzer.is_noise(log), f"Should detect noise: {log}"

    def test_is_important_template(self) -> None:
        """Test template importance detection."""
        analyzer = LogAnalyzer()

        # Important templates
        important_templates = [
            "ERROR Something went wrong",
            "Payment failed for user <NUM>",
            "WARN Connection timeout detected",
            "Subscription renewal failed",
        ]

        for template in important_templates:
            assert analyzer.is_important_template(
                template
            ), f"Should be important: {template}"

        # Non-important templates
        unimportant_templates = [
            "DEBUG Normal operation",
            "Connection established to <IP>",
            "Cache hit for key <ID>",
        ]

        for template in unimportant_templates:
            assert not analyzer.is_important_template(
                template
            ), f"Should not be important: {template}"


@pytest.mark.unit
class TestLogAnalysisHandlers:
    """Test log analysis MCP server handlers."""

    def test_handle_analyze_container_logs_success(
        self,
        mock_docker_client: Mock,
        mock_container: Mock,
    ) -> None:
        """Test successful log analysis through handler."""
        # Mock container logs with realistic data
        log_content = "\n".join(
            [
                "[2025-09-18T20:22:12Z DEBUG hyper::client::pool] pooling idle connection",
                "[2025-09-18T20:22:12Z ERROR payment_service::api] Failed to set payment date",
                "[2025-09-18T20:22:12Z WARN billing_service::subscription] Failed to renew subscription",
                "[2025-09-18T20:22:12Z INFO billing_service::subscription] Subscription activated",
                "[2025-09-18T20:22:12Z DEBUG hyper::proto::h1::io] parsed 9 headers",
            ]
        )

        mock_container.logs.return_value = log_content.encode("utf-8")
        mock_container.short_id = "abc123"
        mock_container.name = "test-container"
        mock_container.status = "running"
        mock_docker_client.containers.get.return_value = mock_container

        # Test the handler
        from mcp_docker_server.input_schemas import AnalyzeContainerLogsInput

        args = AnalyzeContainerLogsInput(container_id="test-container")
        result = _handle_analyze_container_logs(args)

        # Verify structure
        assert "summary" in result
        assert "errors" in result
        assert "warnings" in result
        assert "business_events" in result
        assert "container_info" in result
        assert "analysis_metadata" in result

        # Verify content
        assert len(result["errors"]) == 1
        assert len(result["warnings"]) == 1
        assert "Failed to set payment date" in result["errors"][0]
        assert "Failed to renew subscription" in result["warnings"][0]

        # Verify metadata
        assert result["container_info"]["id"] == "abc123"
        assert result["container_info"]["name"] == "test-container"
        assert result["container_info"]["status"] == "running"
        assert result["analysis_metadata"]["total_lines_analyzed"] == 5

    def test_handle_container_tools_analyze_logs(
        self,
        mock_docker_client: Mock,
        mock_container: Mock,
    ) -> None:
        """Test log analysis through container tools handler."""
        # Setup mock
        log_content = "ERROR Test error\nWARN Test warning"
        mock_container.logs.return_value = log_content.encode("utf-8")
        mock_container.short_id = "abc123"
        mock_container.name = "test-container"
        mock_container.status = "running"
        mock_docker_client.containers.get.return_value = mock_container

        # Test through container tools handler
        arguments = {
            "container_id": "test-container",
            "tail": 100,
            "include_patterns": True,
        }

        result = _handle_container_tools("analyze_container_logs", arguments)

        assert result is not None
        assert "summary" in result
        assert "errors" in result
        assert len(result["errors"]) == 1
        assert "ERROR Test error" in result["errors"][0]

    def test_analyze_logs_with_time_filters(
        self,
        mock_docker_client: Mock,
        mock_container: Mock,
    ) -> None:
        """Test log analysis with time-based filtering."""
        log_content = "ERROR Test error"
        mock_container.logs.return_value = log_content.encode("utf-8")
        mock_docker_client.containers.get.return_value = mock_container

        from mcp_docker_server.input_schemas import AnalyzeContainerLogsInput

        args = AnalyzeContainerLogsInput(
            container_id="test-container", since="1h", until="now"
        )

        result = _handle_analyze_container_logs(args)

        # Verify logs() was called with correct parameters
        mock_container.logs.assert_called_once_with(tail=1000, since="1h", until="now")
        assert result is not None

    def test_analyze_logs_container_not_found(
        self,
        mock_docker_client: Mock,
    ) -> None:
        """Test log analysis when container is not found."""
        from docker.errors import NotFound

        mock_docker_client.containers.get.side_effect = NotFound("Container not found")

        from mcp_docker_server.input_schemas import AnalyzeContainerLogsInput

        args = AnalyzeContainerLogsInput(container_id="nonexistent")

        with pytest.raises(NotFound):
            _handle_analyze_container_logs(args)
