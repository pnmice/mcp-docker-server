"""
Unit tests for Docker tool handlers.
"""

from typing import Any, Dict
from unittest.mock import Mock

import pytest
from docker.errors import NotFound

from mcp_docker_server.server import (
    _handle_container_tools,
    _handle_image_tools,
    _handle_network_tools,
    _handle_volume_tools,
)


@pytest.mark.unit
class TestContainerHandlers:
    """Test container-related tool handlers."""

    def test_list_containers_success(
        self,
        mock_docker_client: Mock,
        mock_container: Mock,
        mock_docker_api_client: Mock,
    ) -> None:
        """Test successful container listing."""
        # Mock raw container data that APIClient.containers() would return
        raw_container_data = [
            {
                "Id": "test_container_id",
                "Names": ["/test_container"],
                "Image": "test:latest",
                "Command": ["test", "command"],
                "Created": 1694876781,
                "Status": "Up 2 hours",
                "Ports": [{"PrivatePort": 80, "Type": "tcp"}],
            }
        ]
        mock_docker_api_client.containers.return_value = raw_container_data

        result = _handle_container_tools("list_containers", {"all": True})

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "test_contain"  # First 12 chars of ID
        assert result[0]["names"] == "test_container"
        assert result[0]["image"] == "test:latest"
        mock_docker_api_client.containers.assert_called_once_with(all=True)

    def test_list_containers_empty(
        self, mock_docker_client: Mock, mock_docker_api_client: Mock
    ) -> None:
        """Test container listing with no containers."""
        mock_docker_api_client.containers.return_value = []

        result = _handle_container_tools("list_containers", {})

        assert result == []
        mock_docker_api_client.containers.assert_called_once()

    def test_create_container_success(
        self,
        mock_docker_client: Mock,
        mock_container: Mock,
        sample_container_args: Dict[str, Any],
    ) -> None:
        """Test successful container creation."""
        mock_docker_client.containers.create.return_value = mock_container

        result = _handle_container_tools("create_container", sample_container_args)

        assert result is not None
        mock_docker_client.containers.create.assert_called_once()

    def test_run_container_success(
        self,
        mock_docker_client: Mock,
        mock_container: Mock,
        sample_container_args: Dict[str, Any],
    ) -> None:
        """Test successful container run."""
        mock_docker_client.containers.run.return_value = mock_container

        result = _handle_container_tools("run_container", sample_container_args)

        assert result is not None
        mock_docker_client.containers.run.assert_called_once()

    def test_recreate_container_success(
        self,
        mock_docker_client: Mock,
        mock_container: Mock,
        sample_container_args: Dict[str, Any],
    ) -> None:
        """Test successful container recreation."""
        # Add container_id to args
        args = {**sample_container_args, "container_id": "test_id"}

        mock_docker_client.containers.get.return_value = mock_container
        mock_docker_client.containers.run.return_value = mock_container

        result = _handle_container_tools("recreate_container", args)

        assert result is not None
        mock_docker_client.containers.get.assert_called_once_with("test_id")
        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()
        mock_docker_client.containers.run.assert_called_once()

    def test_start_container_success(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test successful container start."""
        mock_docker_client.containers.get.return_value = mock_container

        result = _handle_container_tools("start_container", {"container_id": "test_id"})

        assert result is not None
        mock_docker_client.containers.get.assert_called_once_with("test_id")
        mock_container.start.assert_called_once()

    def test_stop_container_success(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test successful container stop."""
        mock_docker_client.containers.get.return_value = mock_container

        result = _handle_container_tools("stop_container", {"container_id": "test_id"})

        assert result is not None
        mock_docker_client.containers.get.assert_called_once_with("test_id")
        mock_container.stop.assert_called_once()

    def test_remove_container_success(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test successful container removal."""
        mock_docker_client.containers.get.return_value = mock_container

        result = _handle_container_tools(
            "remove_container", {"container_id": "test_id", "force": False}
        )

        assert result is not None
        mock_docker_client.containers.get.assert_called_once_with("test_id")
        mock_container.remove.assert_called_once_with(force=False)

    def test_fetch_container_logs_success(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test successful container log fetching."""
        mock_docker_client.containers.get.return_value = mock_container
        mock_container.logs.return_value = b"log line 1\nlog line 2\n"

        result = _handle_container_tools(
            "fetch_container_logs", {"container_id": "test_id", "tail": 100}
        )

        assert result is not None
        assert "logs" in result
        assert result["logs"] == ["log line 1", "log line 2", ""]
        mock_docker_client.containers.get.assert_called_once_with("test_id")
        mock_container.logs.assert_called_once_with(tail=100)

    def test_container_not_found(self, mock_docker_client: Mock) -> None:
        """Test handling of container not found error."""
        mock_docker_client.containers.get.side_effect = NotFound("Container not found")

        with pytest.raises(NotFound):
            _handle_container_tools("start_container", {"container_id": "nonexistent"})

    def test_unknown_container_tool(self) -> None:
        """Test handling of unknown container tool."""
        result = _handle_container_tools("unknown_tool", {})
        assert result is None


@pytest.mark.unit
class TestImageHandlers:
    """Test image-related tool handlers."""

    def test_list_images_success(
        self, mock_docker_client: Mock, mock_image: Mock, mock_docker_api_client: Mock
    ) -> None:
        """Test successful image listing."""
        # Mock raw image data that APIClient.images() would return
        raw_image_data = [
            {
                "Id": "sha256:test_image_id",
                "RepoTags": ["test:latest"],
                "Created": 1694876781,
                "Size": 123456789,
                "VirtualSize": 123456789,
                "Labels": {"test": "label"},
            }
        ]
        mock_docker_api_client.images.return_value = raw_image_data

        result = _handle_image_tools("list_images", {"all": True})

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "test_image_i"  # First 12 chars after sha256:
        assert result[0]["repo_tags"] == ["test:latest"]
        assert result[0]["size"] == 123456789
        mock_docker_api_client.images.assert_called_once_with(all=True)

    def test_pull_image_success(
        self,
        mock_docker_client: Mock,
        mock_image: Mock,
        sample_image_args: Dict[str, str],
    ) -> None:
        """Test successful image pull."""
        mock_docker_client.images.pull.return_value = mock_image

        result = _handle_image_tools("pull_image", sample_image_args)

        assert result is not None
        mock_docker_client.images.pull.assert_called_once_with("nginx", tag="latest")

    def test_push_image_success(
        self, mock_docker_client: Mock, sample_image_args: Dict[str, str]
    ) -> None:
        """Test successful image push."""
        result = _handle_image_tools("push_image", sample_image_args)

        assert result is not None
        assert result["status"] == "pushed"
        assert result["repository"] == "nginx"
        assert result["tag"] == "latest"
        mock_docker_client.images.push.assert_called_once_with("nginx", tag="latest")

    def test_build_image_success(
        self, mock_docker_client: Mock, mock_image: Mock
    ) -> None:
        """Test successful image build."""
        build_logs = [
            {"stream": "Step 1/2 : FROM alpine\n"},
            {"stream": "Successfully built\n"},
        ]
        mock_docker_client.images.build.return_value = (mock_image, build_logs)

        result = _handle_image_tools(
            "build_image", {"path": "/tmp", "tag": "test:latest"}
        )

        assert result is not None
        assert "image" in result
        assert "logs" in result
        assert result["logs"] == build_logs
        mock_docker_client.images.build.assert_called_once_with(
            path="/tmp", tag="test:latest"
        )

    def test_remove_image_success(self, mock_docker_client: Mock) -> None:
        """Test successful image removal."""
        result = _handle_image_tools(
            "remove_image", {"image": "test:latest", "force": False}
        )

        assert result is not None
        assert result["status"] == "removed"
        assert result["image"] == "test:latest"
        mock_docker_client.images.remove.assert_called_once_with(
            image="test:latest", force=False
        )

    def test_unknown_image_tool(self) -> None:
        """Test handling of unknown image tool."""
        result = _handle_image_tools("unknown_tool", {})
        assert result is None


@pytest.mark.unit
class TestNetworkHandlers:
    """Test network-related tool handlers."""

    def test_list_networks_success(
        self, mock_docker_client: Mock, mock_network: Mock, mock_docker_api_client: Mock
    ) -> None:
        """Test successful network listing."""
        # Mock raw network data that APIClient.networks() would return
        raw_network_data = [
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
        mock_docker_api_client.networks.return_value = raw_network_data

        result = _handle_network_tools("list_networks", {})

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["id"] == "test_network"  # First 12 chars
        assert result[0]["name"] == "test_network"
        assert result[0]["driver"] == "bridge"
        mock_docker_api_client.networks.assert_called_once()

    def test_create_network_success(
        self,
        mock_docker_client: Mock,
        mock_network: Mock,
        sample_network_args: Dict[str, str],
    ) -> None:
        """Test successful network creation."""
        mock_docker_client.networks.create.return_value = mock_network

        result = _handle_network_tools("create_network", sample_network_args)

        assert result is not None
        mock_docker_client.networks.create.assert_called_once_with(
            name="test_network", driver="bridge", internal=False
        )

    def test_remove_network_success(
        self, mock_docker_client: Mock, mock_network: Mock
    ) -> None:
        """Test successful network removal."""
        mock_docker_client.networks.get.return_value = mock_network

        result = _handle_network_tools(
            "remove_network", {"network_id": "test_network_id"}
        )

        assert result is not None
        mock_docker_client.networks.get.assert_called_once_with("test_network_id")
        mock_network.remove.assert_called_once()

    def test_unknown_network_tool(self) -> None:
        """Test handling of unknown network tool."""
        result = _handle_network_tools("unknown_tool", {})
        assert result is None


@pytest.mark.unit
class TestVolumeHandlers:
    """Test volume-related tool handlers."""

    def test_list_volumes_success(
        self, mock_docker_client: Mock, mock_volume: Mock, mock_docker_api_client: Mock
    ) -> None:
        """Test successful volume listing."""
        # Mock raw volume data that APIClient.volumes() would return
        raw_volumes_response = {
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
        mock_docker_api_client.volumes.return_value = raw_volumes_response

        result = _handle_volume_tools("list_volumes", {})

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["name"] == "test_volume"
        assert result[0]["driver"] == "local"
        assert result[0]["scope"] == "local"
        mock_docker_api_client.volumes.assert_called_once()

    def test_create_volume_success(
        self,
        mock_docker_client: Mock,
        mock_volume: Mock,
        sample_volume_args: Dict[str, str],
    ) -> None:
        """Test successful volume creation."""
        mock_docker_client.volumes.create.return_value = mock_volume

        result = _handle_volume_tools("create_volume", sample_volume_args)

        assert result is not None
        mock_docker_client.volumes.create.assert_called_once_with(
            name="test_volume", driver="local"
        )

    def test_remove_volume_success(
        self, mock_docker_client: Mock, mock_volume: Mock
    ) -> None:
        """Test successful volume removal."""
        mock_docker_client.volumes.get.return_value = mock_volume

        result = _handle_volume_tools(
            "remove_volume", {"volume_name": "test_volume", "force": False}
        )

        assert result is not None
        mock_docker_client.volumes.get.assert_called_once_with("test_volume")
        mock_volume.remove.assert_called_once_with(force=False)

    def test_unknown_volume_tool(self) -> None:
        """Test handling of unknown volume tool."""
        result = _handle_volume_tools("unknown_tool", {})
        assert result is None
