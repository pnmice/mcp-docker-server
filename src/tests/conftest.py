"""
Test configuration and fixtures for mcp-docker-server.
"""

import asyncio
import sys
from pathlib import Path
from typing import Any, Dict, Generator
from unittest.mock import AsyncMock, Mock

import docker
import pytest
from mcp.server import Server

from mcp_docker_server.server import app
from mcp_docker_server.settings import ServerSettings

# Add src directory to Python path for testing
src_path = Path(__file__).parent.parent
sys.path.insert(0, str(src_path))


@pytest.fixture
def mock_docker_client() -> Mock:
    """Mock Docker client for unit tests."""
    client = Mock(spec=docker.DockerClient)

    # Mock containers
    client.containers = Mock()
    client.containers.list = Mock(return_value=[])
    client.containers.get = Mock()
    client.containers.create = Mock()
    client.containers.run = Mock()

    # Mock images
    client.images = Mock()
    client.images.list = Mock(return_value=[])
    client.images.get = Mock()
    client.images.pull = Mock()
    client.images.push = Mock()
    client.images.build = Mock()
    client.images.remove = Mock()

    # Mock networks
    client.networks = Mock()
    client.networks.list = Mock(return_value=[])
    client.networks.get = Mock()
    client.networks.create = Mock()

    # Mock volumes
    client.volumes = Mock()
    client.volumes.list = Mock(return_value=[])
    client.volumes.get = Mock()
    client.volumes.create = Mock()

    return client


@pytest.fixture
def mock_container() -> Mock:
    """Mock Docker container object."""
    container = Mock()
    container.id = "test_container_id"
    container.name = "/test_container"
    container.short_id = "test_container_short"
    container.status = "running"
    container.image = Mock()
    container.image.tags = ["test:latest"]
    container.labels = {}
    container.ports = {}
    container.mounts = []
    container.attrs = {
        "Id": "test_container_id",
        "Name": "/test_container",
        "Config": {"Image": "test:latest", "Cmd": ["test", "command"]},
        "State": {"Status": "running"},
        "NetworkSettings": {"Ports": {}},
        "Mounts": [],
        "Created": "2025-09-16T19:26:21.553367722Z",
    }
    container.start = Mock()
    container.stop = Mock()
    container.remove = Mock()
    container.logs = Mock(return_value=b"test logs")
    container.stats = Mock(return_value={"cpu_stats": {}})
    return container


@pytest.fixture
def mock_image() -> Mock:
    """Mock Docker image object."""
    image = Mock()
    image.id = "test_image_id"
    image.short_id = "test_image_short"
    image.tags = ["test:latest"]
    image.labels = {}
    image.attrs = {
        "Id": "test_image_id",
        "RepoTags": ["test:latest"],
        "RepoDigests": [],
        "Labels": {},
        "Created": "2023-01-01T00:00:00Z",
        "Size": 1000000,
    }
    return image


@pytest.fixture
def mock_network() -> Mock:
    """Mock Docker network object."""
    network = Mock()
    network.id = "test_network_id"
    network.name = "test_network"
    network.attrs = {
        "Id": "test_network_id",
        "Name": "test_network",
        "Driver": "bridge",
        "Labels": {},
    }
    network.remove = Mock()
    return network


@pytest.fixture
def mock_volume() -> Mock:
    """Mock Docker volume object."""
    volume = Mock()
    volume.id = "test_volume_id"
    volume.name = "test_volume"
    volume.attrs = {
        "Name": "test_volume",
        "Driver": "local",
        "Labels": {},
        "Mountpoint": "/var/lib/docker/volumes/test_volume/_data",
    }
    volume.remove = Mock()
    return volume


@pytest.fixture
def sample_container_args() -> Dict[str, Any]:
    """Sample arguments for container operations."""
    return {
        "image": "nginx:latest",
        "name": "test_nginx",
        "ports": {"80/tcp": 8080},
        "environment": {"ENV": "test"},
        "detach": True,
    }


@pytest.fixture
def sample_image_args() -> Dict[str, str]:
    """Sample arguments for image operations."""
    return {"repository": "nginx", "tag": "latest"}


@pytest.fixture
def sample_network_args() -> Dict[str, str]:
    """Sample arguments for network operations."""
    return {"name": "test_network", "driver": "bridge"}


@pytest.fixture
def sample_volume_args() -> Dict[str, str]:
    """Sample arguments for volume operations."""
    return {"name": "test_volume", "driver": "local"}


@pytest.fixture
def server_settings() -> ServerSettings:
    """Sample server settings."""
    return ServerSettings()


@pytest.fixture
def mcp_server() -> Server:
    """Create MCP server instance for testing."""
    return app


@pytest.fixture
def mock_session() -> AsyncMock:
    """Mock MCP session for testing."""
    session = AsyncMock()
    session.send_log_message = AsyncMock()
    return session


@pytest.fixture
def mock_docker_api_client() -> Mock:
    """Mock Docker APIClient for unit tests."""
    from docker.api import APIClient

    api_client = Mock(spec=APIClient)

    # Mock containers method to return raw container data
    api_client.containers = Mock(return_value=[])

    return api_client


@pytest.fixture(autouse=True)
def patch_docker_client(
    monkeypatch: Any, mock_docker_client: Mock, mock_docker_api_client: Mock
) -> Mock:
    """Automatically patch the global Docker client for all tests."""
    # Initialize _docker as None if it doesn't exist
    import mcp_docker_server.server as server_module

    if not hasattr(server_module, "_docker"):
        server_module._docker = None

    if not hasattr(server_module, "_docker_api"):
        server_module._docker_api = None

    monkeypatch.setattr("mcp_docker_server.server._docker", mock_docker_client)
    monkeypatch.setattr("mcp_docker_server.server._docker_api", mock_docker_api_client)
    return mock_docker_client


@pytest.fixture(autouse=True)
def patch_request_context(monkeypatch: Any) -> None:
    """Automatically patch the request context for all tests."""
    from unittest.mock import AsyncMock, Mock, PropertyMock

    mock_session = AsyncMock()
    mock_session.send_log_message = AsyncMock()

    mock_context = Mock()
    mock_context.session = mock_session

    # Patch the request_context property to return our mock
    mock_request_context = PropertyMock(return_value=mock_context)

    import mcp_docker_server.server as server_module

    monkeypatch.setattr(
        type(server_module.app), "request_context", mock_request_context
    )


@pytest.fixture
def event_loop() -> Generator[asyncio.AbstractEventLoop, None, None]:
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# Define pytest markers
def pytest_configure(config: Any) -> None:
    """Configure pytest markers."""
    config.addinivalue_line("markers", "unit: Unit tests")
    config.addinivalue_line("markers", "integration: Integration tests")
    config.addinivalue_line("markers", "slow: Slow tests")
    config.addinivalue_line("markers", "network: Network-dependent tests")
