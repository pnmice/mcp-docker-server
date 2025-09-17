"""
Tests for the main MCP server functionality.
"""

import json
from unittest.mock import Mock

import pytest
from mcp import types

from mcp_docker_server.server import (
    call_tool,
    get_prompt,
    list_prompts,
    list_resources,
    list_tools,
    read_resource,
)


@pytest.mark.unit
class TestMcpServer:
    """Test MCP server core functionality."""

    @pytest.mark.asyncio
    async def test_list_tools(self) -> None:
        """Test listing all available tools."""
        tools = await list_tools()

        assert isinstance(tools, list)
        assert len(tools) > 0

        tool_names = [tool.name for tool in tools]
        expected_tools = [
            "list_containers",
            "create_container",
            "run_container",
            "recreate_container",
            "start_container",
            "stop_container",
            "remove_container",
            "fetch_container_logs",
            "list_images",
            "pull_image",
            "push_image",
            "build_image",
            "remove_image",
            "list_networks",
            "create_network",
            "remove_network",
            "list_volumes",
            "create_volume",
            "remove_volume",
            "get_docker_disk_usage",
            "get_container_stats",
        ]

        for expected_tool in expected_tools:
            assert expected_tool in tool_names

    @pytest.mark.asyncio
    async def test_list_resources(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test listing resources."""
        mock_container.id = "test_id"
        mock_container.name = "test_container"
        mock_docker_client.containers.list.return_value = [mock_container]

        resources = await list_resources()

        assert isinstance(resources, list)
        assert (
            len(resources) == 0
        )  # Resources list is now empty to prevent token overflow

        # Resources are now accessed via list_containers tool instead

    @pytest.mark.asyncio
    async def test_read_resource_logs(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test reading container logs resource."""
        mock_container.logs.return_value = b"log line 1\nlog line 2\n"
        mock_docker_client.containers.get.return_value = mock_container

        uri = types.AnyUrl("docker://containers/test_id/logs")
        result = await read_resource(uri)

        assert isinstance(result, str)
        parsed_result = json.loads(result)
        assert parsed_result == ["log line 1", "log line 2", ""]

    @pytest.mark.asyncio
    async def test_read_resource_stats(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test reading container stats resource."""
        stats_data = {"cpu_stats": {"cpu_usage": {"total_usage": 1000}}}
        mock_container.stats.return_value = stats_data
        mock_docker_client.containers.get.return_value = mock_container

        uri = types.AnyUrl("docker://containers/test_id/stats")
        result = await read_resource(uri)

        assert isinstance(result, str)
        parsed_result = json.loads(result)
        assert parsed_result == stats_data

    @pytest.mark.asyncio
    async def test_read_resource_invalid_uri(self) -> None:
        """Test reading resource with invalid URI."""
        uri = types.AnyUrl("invalid://uri")

        with pytest.raises(ValueError, match="Unknown resource URI"):
            await read_resource(uri)

    @pytest.mark.asyncio
    async def test_read_resource_invalid_format(self) -> None:
        """Test reading resource with invalid format."""
        uri = types.AnyUrl("docker://containers/invalid")

        with pytest.raises(ValueError, match="Invalid container resource URI"):
            await read_resource(uri)

    @pytest.mark.asyncio
    async def test_list_prompts(self) -> None:
        """Test listing available prompts."""
        prompts = await list_prompts()

        assert isinstance(prompts, list)
        assert len(prompts) == 1
        assert prompts[0].name == "docker_compose"

    @pytest.mark.asyncio
    async def test_get_prompt_docker_compose(self, mock_docker_client: Mock) -> None:
        """Test getting docker_compose prompt."""
        # Mock empty resources for the prompt
        mock_docker_client.containers.list.return_value = []
        mock_docker_client.volumes.list.return_value = []
        mock_docker_client.networks.list.return_value = []

        arguments = {"name": "test_project", "containers": "nginx container"}
        result = await get_prompt("docker_compose", arguments)

        assert isinstance(result, types.GetPromptResult)
        assert len(result.messages) == 1
        assert result.messages[0].role == "user"
        assert "test_project" in result.messages[0].content.text  # type: ignore[union-attr]

    @pytest.mark.asyncio
    async def test_get_prompt_unknown(self) -> None:
        """Test getting unknown prompt."""
        with pytest.raises(ValueError, match="Unknown prompt name"):
            await get_prompt("unknown_prompt", {})


@pytest.mark.unit
class TestCallTool:
    """Test the main call_tool function."""

    @pytest.mark.asyncio
    async def test_call_tool_container_success(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test successful container tool call."""
        mock_docker_client.containers.list.return_value = [mock_container]

        result = await call_tool("list_containers", {})

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)

        # Parse the JSON response
        response_data = json.loads(result[0].text)
        assert isinstance(response_data, list)

    @pytest.mark.asyncio
    async def test_call_tool_image_success(
        self, mock_docker_client: Mock, mock_image: Mock, mock_docker_api_client: Mock
    ) -> None:
        """Test successful image tool call."""
        mock_docker_api_client.images.return_value = [
            {
                "Id": "sha256:test_image_id123",
                "RepoTags": ["test:latest"],
                "Created": 1694876781,
                "Size": 123456789,
                "VirtualSize": 123456789,
                "Labels": {"test": "label"},
            }
        ]

        result = await call_tool("list_images", {})

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)

    @pytest.mark.asyncio
    async def test_call_tool_network_success(
        self, mock_docker_client: Mock, mock_network: Mock, mock_docker_api_client: Mock
    ) -> None:
        """Test successful network tool call."""
        mock_docker_api_client.networks.return_value = [
            {
                "Id": "test_network_id123",
                "Name": "test_network",
                "Driver": "bridge",
                "Scope": "local",
                "Created": "2025-09-16T15:00:00Z",
                "Labels": {"test": "label"},
                "Options": {"test": "option"},
                "IPAM": {"Driver": "default"},
            }
        ]

        result = await call_tool("list_networks", {})

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)

    @pytest.mark.asyncio
    async def test_call_tool_volume_success(
        self, mock_docker_client: Mock, mock_volume: Mock, mock_docker_api_client: Mock
    ) -> None:
        """Test successful volume tool call."""
        mock_docker_api_client.volumes.return_value = {
            "Volumes": [
                {
                    "Name": "test_volume",
                    "Driver": "local",
                    "Mountpoint": "/var/lib/docker/volumes/test_volume/_data",
                    "CreatedAt": "2025-09-16T15:00:00Z",
                    "Labels": {"test": "label"},
                    "Options": {"test": "option"},
                    "Scope": "local",
                }
            ]
        }

        result = await call_tool("list_volumes", {})

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)

    @pytest.mark.asyncio
    async def test_call_tool_unknown_tool(self) -> None:
        """Test calling unknown tool."""
        result = await call_tool("unknown_tool", {})

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)
        assert "Unknown tool: unknown_tool" in result[0].text

    @pytest.mark.asyncio
    async def test_call_tool_validation_error(self, mock_docker_client: Mock) -> None:
        """Test tool call with validation error."""
        # Pass invalid arguments that will cause validation error
        result = await call_tool("create_container", {"invalid_field": "value"})

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)
        assert "ERROR: You provided invalid Tool inputs" in result[0].text

        # Verify error was logged (using the autouse fixture's mock)
        from mcp_docker_server.server import app

        app.request_context.session.send_log_message.assert_called_once()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_call_tool_none_arguments(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test tool call with None arguments."""
        mock_docker_client.containers.list.return_value = [mock_container]

        result = await call_tool("list_containers", None)

        assert isinstance(result, list)
        assert len(result) == 1
        assert isinstance(result[0], types.TextContent)

    @pytest.mark.asyncio
    async def test_call_tool_docker_error(
        self, mock_docker_client: Mock, mock_docker_api_client: Mock
    ) -> None:
        """Test tool call with Docker API error."""
        from docker.errors import APIError

        mock_docker_api_client.containers.side_effect = APIError("Docker daemon error")

        with pytest.raises(APIError):
            await call_tool("list_containers", {})

        # Verify error was logged (using the autouse fixture's mock)
        from mcp_docker_server.server import app

        app.request_context.session.send_log_message.assert_called_once()  # type: ignore[attr-defined]
