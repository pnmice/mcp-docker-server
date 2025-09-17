"""
Integration tests for mcp-docker-server.
These tests require Docker to be running.
"""

import docker
import pytest
from docker.errors import DockerException

from mcp_docker_server.server import call_tool


@pytest.fixture(scope="session")
def real_docker_client() -> docker.DockerClient:
    """Get real Docker client if available, skip tests if not."""
    try:
        client = docker.from_env()
        client.ping()
        return client
    except DockerException:
        pytest.skip("Docker is not available")


@pytest.fixture
def test_image_name() -> str:
    """Name for test images."""
    return "alpine:latest"


@pytest.fixture
def test_container_name() -> str:
    """Name for test containers."""
    return "mcp-test-container"


@pytest.fixture
def test_network_name() -> str:
    """Name for test networks."""
    return "mcp-test-network"


@pytest.fixture
def test_volume_name() -> str:
    """Name for test volumes."""
    return "mcp-test-volume"


@pytest.mark.integration
@pytest.mark.slow
class TestDockerIntegration:
    """Integration tests with real Docker."""

    @pytest.mark.asyncio
    async def test_full_container_lifecycle(
        self,
        real_docker_client: docker.DockerClient,
        test_image_name: str,
        test_container_name: str,
    ) -> None:
        """Test complete container lifecycle: create, start, stop, remove."""
        # Ensure we have the test image
        try:
            real_docker_client.images.get(test_image_name)
        except docker.errors.ImageNotFound:
            real_docker_client.images.pull(test_image_name)

        # Clean up any existing test container
        try:
            existing = real_docker_client.containers.get(test_container_name)
            existing.remove(force=True)
        except docker.errors.NotFound:
            pass

        # Patch the global docker client for our tests
        import mcp_docker_server.server

        original_docker = mcp_docker_server.server._docker
        original_docker_api = mcp_docker_server.server._docker_api
        mcp_docker_server.server._docker = real_docker_client
        mcp_docker_server.server._docker_api = real_docker_client.api

        try:
            # Create container
            create_args = {
                "image": test_image_name,
                "name": test_container_name,
                "command": "sleep 30",
                "detach": True,
            }
            result = await call_tool("create_container", create_args)
            assert len(result) == 1

            # Start container
            start_args = {"container_id": test_container_name}
            result = await call_tool("start_container", start_args)
            assert len(result) == 1

            # Verify container is running
            container = real_docker_client.containers.get(test_container_name)
            assert container.status == "running"

            # Stop container
            result = await call_tool("stop_container", start_args)
            assert len(result) == 1

            # Remove container
            remove_args = {"container_id": test_container_name, "force": False}
            result = await call_tool("remove_container", remove_args)
            assert len(result) == 1

        finally:
            # Restore original docker client
            mcp_docker_server.server._docker = original_docker
            mcp_docker_server.server._docker_api = original_docker_api

            # Clean up
            try:
                container = real_docker_client.containers.get(test_container_name)
                container.remove(force=True)
            except docker.errors.NotFound:
                pass

    @pytest.mark.asyncio
    async def test_image_operations(
        self, real_docker_client: docker.DockerClient, test_image_name: str
    ) -> None:
        """Test image listing and pulling."""
        import mcp_docker_server.server

        original_docker = mcp_docker_server.server._docker
        original_docker_api = mcp_docker_server.server._docker_api
        mcp_docker_server.server._docker = real_docker_client
        mcp_docker_server.server._docker_api = real_docker_client.api

        try:
            # List images
            result = await call_tool("list_images", {})
            assert len(result) == 1

            # Pull image (should work even if already exists)
            pull_args = {"repository": "alpine", "tag": "latest"}
            result = await call_tool("pull_image", pull_args)
            assert len(result) == 1

        finally:
            mcp_docker_server.server._docker = original_docker
            mcp_docker_server.server._docker_api = original_docker_api

    @pytest.mark.asyncio
    async def test_network_operations(
        self, real_docker_client: docker.DockerClient, test_network_name: str
    ) -> None:
        """Test network creation and removal."""
        # Clean up any existing test network
        try:
            existing = real_docker_client.networks.get(test_network_name)
            existing.remove()
        except docker.errors.NotFound:
            pass

        import mcp_docker_server.server

        original_docker = mcp_docker_server.server._docker
        original_docker_api = mcp_docker_server.server._docker_api
        mcp_docker_server.server._docker = real_docker_client
        mcp_docker_server.server._docker_api = real_docker_client.api

        try:
            # Create network
            create_args = {"name": test_network_name, "driver": "bridge"}
            result = await call_tool("create_network", create_args)
            assert len(result) == 1

            # List networks
            result = await call_tool("list_networks", {})
            assert len(result) == 1

            # Remove network
            remove_args = {"network_id": test_network_name}
            result = await call_tool("remove_network", remove_args)
            assert len(result) == 1

        finally:
            mcp_docker_server.server._docker = original_docker
            mcp_docker_server.server._docker_api = original_docker_api

            # Clean up
            try:
                network = real_docker_client.networks.get(test_network_name)
                network.remove()
            except docker.errors.NotFound:
                pass

    @pytest.mark.asyncio
    async def test_volume_operations(
        self, real_docker_client: docker.DockerClient, test_volume_name: str
    ) -> None:
        """Test volume creation and removal."""
        # Clean up any existing test volume
        try:
            existing = real_docker_client.volumes.get(test_volume_name)
            existing.remove()
        except docker.errors.NotFound:
            pass

        import mcp_docker_server.server

        original_docker = mcp_docker_server.server._docker
        original_docker_api = mcp_docker_server.server._docker_api
        mcp_docker_server.server._docker = real_docker_client
        mcp_docker_server.server._docker_api = real_docker_client.api

        try:
            # Create volume
            create_args = {"name": test_volume_name, "driver": "local"}
            result = await call_tool("create_volume", create_args)
            assert len(result) == 1

            # List volumes
            result = await call_tool("list_volumes", {})
            assert len(result) == 1

            # Remove volume
            remove_args = {"volume_name": test_volume_name, "force": False}
            result = await call_tool("remove_volume", remove_args)
            assert len(result) == 1

        finally:
            mcp_docker_server.server._docker = original_docker
            mcp_docker_server.server._docker_api = original_docker_api

            # Clean up
            try:
                volume = real_docker_client.volumes.get(test_volume_name)
                volume.remove()
            except docker.errors.NotFound:
                pass


@pytest.mark.integration
class TestInputValidation:
    """Test input validation and error handling."""

    @pytest.mark.asyncio
    async def test_invalid_container_args(self) -> None:
        """Test handling of invalid container arguments."""
        # Missing required image field
        result = await call_tool("create_container", {"name": "test"})
        assert len(result) == 1
        assert "ERROR: You provided invalid Tool inputs" in result[0].text

    @pytest.mark.asyncio
    async def test_invalid_image_args(self) -> None:
        """Test handling of invalid image arguments."""
        # Missing required repository field
        result = await call_tool("pull_image", {"tag": "latest"})
        assert len(result) == 1
        assert "ERROR: You provided invalid Tool inputs" in result[0].text

    @pytest.mark.asyncio
    async def test_invalid_network_args(self) -> None:
        """Test handling of invalid network arguments."""
        # Missing required name field
        result = await call_tool("create_network", {"driver": "bridge"})
        assert len(result) == 1
        assert "ERROR: You provided invalid Tool inputs" in result[0].text

    @pytest.mark.asyncio
    async def test_invalid_volume_args(self) -> None:
        """Test handling of invalid volume arguments."""
        # Missing required name field
        result = await call_tool("create_volume", {"driver": "local"})
        assert len(result) == 1
        assert "ERROR: You provided invalid Tool inputs" in result[0].text
