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
    _handle_system_tools,
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

    def test_fetch_container_logs_with_grep_filter(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test container log fetching with grep filtering."""
        # Set up mock container with specific logs for this test
        mock_container.logs.return_value = b"INFO: Starting application\nERROR: Database connection failed\nINFO: Retrying connection\nERROR: Still failing\n"
        mock_docker_client.containers.get.return_value = mock_container

        result = _handle_container_tools(
            "fetch_container_logs",
            {"container_id": "test_id", "tail": 100, "grep": "ERROR"},
        )

        assert result is not None
        assert "logs" in result
        assert len(result["logs"]) == 2
        assert "ERROR: Database connection failed" in result["logs"]
        assert "ERROR: Still failing" in result["logs"]
        mock_docker_client.containers.get.assert_called_once_with("test_id")
        mock_container.logs.assert_called_once_with(tail=100)

    def test_fetch_container_logs_with_time_filters(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test container log fetching with time range filters."""
        mock_docker_client.containers.get.return_value = mock_container
        mock_container.logs.return_value = b"log line 1\nlog line 2\n"

        result = _handle_container_tools(
            "fetch_container_logs",
            {
                "container_id": "test_id",
                "tail": 100,
                "since": "2023-01-01T00:00:00Z",
                "until": "2023-12-31T23:59:59Z",
            },
        )

        assert result is not None
        assert "logs" in result
        assert result["logs"] == ["log line 1", "log line 2", ""]
        mock_docker_client.containers.get.assert_called_once_with("test_id")
        mock_container.logs.assert_called_once_with(
            tail=100, since="2023-01-01T00:00:00Z", until="2023-12-31T23:59:59Z"
        )

    def test_fetch_container_logs_grep_case_insensitive(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test container log grep filtering is case-insensitive."""
        mock_docker_client.containers.get.return_value = mock_container
        mock_container.logs.return_value = (
            b"Error: Something failed\nerror: Another issue\nINFO: All good\n"
        )

        result = _handle_container_tools(
            "fetch_container_logs",
            {"container_id": "test_id", "tail": 100, "grep": "error"},
        )

        assert result is not None
        assert "logs" in result
        assert len(result["logs"]) == 2
        assert "Error: Something failed" in result["logs"]
        assert "error: Another issue" in result["logs"]

    def test_fetch_container_logs_no_matches(
        self, mock_docker_client: Mock, mock_container: Mock
    ) -> None:
        """Test container log fetching when grep pattern matches nothing."""
        mock_docker_client.containers.get.return_value = mock_container
        mock_container.logs.return_value = (
            b"INFO: Starting application\nINFO: Everything is fine\n"
        )

        result = _handle_container_tools(
            "fetch_container_logs",
            {"container_id": "test_id", "tail": 100, "grep": "ERROR"},
        )

        assert result is not None
        assert "logs" in result
        assert result["logs"] == []

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


@pytest.mark.unit
class TestSystemHandlers:
    """Test system-related tool handlers."""

    def test_get_docker_disk_usage_basic(
        self,
        mock_docker_client: Mock,
        mock_docker_api_client: Mock,
    ) -> None:
        """Test basic Docker disk usage without verbose mode."""
        # Mock images data
        mock_images_data = [
            {
                "Id": "sha256:image1",
                "Size": 1000000,
                "VirtualSize": 1200000,
                "RepoTags": ["test:latest"],
                "Created": 1694876781,
            },
            {
                "Id": "sha256:image2",
                "Size": 2000000,
                "VirtualSize": 2500000,
                "RepoTags": ["unused:latest"],
                "Created": 1694876780,
            },
        ]
        mock_docker_api_client.images.return_value = mock_images_data

        # Mock containers data
        mock_containers_data = [
            {
                "Id": "container1",
                "ImageID": "sha256:image1",  # Active image
                "State": "running",
                "SizeRw": 50000,
                "Names": ["/test_container"],
                "Image": "test:latest",
                "Command": ["test"],
                "Created": 1694876781,
                "Status": "Up 2 hours",
                "Mounts": [
                    {"Type": "volume", "Name": "test_volume"},
                    {"Type": "bind", "Source": "/host/path"},
                ],
            }
        ]
        mock_docker_api_client.containers.return_value = mock_containers_data

        # Mock volumes data
        mock_volumes_data = {
            "Volumes": [
                {"Name": "test_volume"},
                {"Name": "unused_volume"},
            ]
        }
        mock_docker_api_client.volumes.return_value = mock_volumes_data

        result = _handle_system_tools("get_docker_disk_usage", {"verbose": False})

        assert result is not None
        assert result["type"] == "summary"
        assert "data" in result

        data = result["data"]
        assert len(data) == 4  # Images, Containers, Local Volumes, Build Cache

        # Check images summary
        images_summary = next(item for item in data if item["type"] == "Images")
        assert images_summary["total"] == 2
        assert images_summary["active"] == 1  # Only image1 is used by container
        assert images_summary["size"] == 3000000  # Total size of both images
        assert images_summary["reclaimable"] == 2000000  # Size of unused image2

        # Check containers summary
        containers_summary = next(item for item in data if item["type"] == "Containers")
        assert containers_summary["total"] == 1
        assert containers_summary["active"] == 1  # One running container
        assert containers_summary["size"] == 50000
        assert containers_summary["reclaimable"] == 0

        # Check volumes summary
        volumes_summary = next(item for item in data if item["type"] == "Local Volumes")
        assert volumes_summary["total"] == 2
        assert volumes_summary["active"] == 1  # test_volume is used

        # Verify API calls
        mock_docker_api_client.images.assert_called_once()
        mock_docker_api_client.containers.assert_called_once_with(all=True)
        mock_docker_api_client.volumes.assert_called_once()

    def test_get_docker_disk_usage_verbose(
        self,
        mock_docker_client: Mock,
        mock_docker_api_client: Mock,
    ) -> None:
        """Test Docker disk usage with verbose mode."""
        # Mock images data
        mock_images_data = [
            {
                "Id": "sha256:image1",
                "Size": 1000000,
                "VirtualSize": 1200000,
                "RepoTags": ["test:latest"],
                "Created": 1694876781,
            },
        ]
        mock_docker_api_client.images.return_value = mock_images_data

        # Mock containers data
        mock_containers_data = [
            {
                "Id": "container1",
                "ImageID": "sha256:image1",
                "State": "running",
                "SizeRw": 50000,
                "Names": ["/test_container"],
                "Image": "test:latest",
                "Command": ["test", "command"],
                "Created": 1694876781,
                "Status": "Up 2 hours",
                "Mounts": [{"Type": "volume", "Name": "test_volume"}],
            }
        ]
        mock_docker_api_client.containers.return_value = mock_containers_data

        # Mock volumes data
        mock_volumes_data = {
            "Volumes": [
                {"Name": "test_volume"},
            ]
        }
        mock_docker_api_client.volumes.return_value = mock_volumes_data

        result = _handle_system_tools("get_docker_disk_usage", {"verbose": True})

        assert result is not None
        assert result["type"] == "summary"
        assert "detailed" in result

        detailed = result["detailed"]

        # Check detailed images
        assert "images" in detailed
        images = detailed["images"]
        assert len(images) == 1
        assert images[0]["repository"] == "test"
        assert images[0]["tag"] == "latest"
        assert images[0]["size"] == 1000000
        assert images[0]["containers"] == 1

        # Check detailed containers
        assert "containers" in detailed
        containers = detailed["containers"]
        assert len(containers) == 1
        assert containers[0]["image"] == "test:latest"
        assert containers[0]["command"] == "test"
        assert containers[0]["local_volumes"] == 1
        assert containers[0]["names"] == "test_container"

        # Check detailed volumes
        assert "volumes" in detailed
        volumes = detailed["volumes"]
        assert len(volumes) == 1
        assert volumes[0]["volume_name"] == "test_volume"
        assert volumes[0]["links"] == 1

    def test_get_docker_disk_usage_no_data(
        self,
        mock_docker_client: Mock,
        mock_docker_api_client: Mock,
    ) -> None:
        """Test Docker disk usage with no images/containers/volumes."""
        # Mock empty data
        mock_docker_api_client.images.return_value = []
        mock_docker_api_client.containers.return_value = []
        mock_docker_api_client.volumes.return_value = {"Volumes": []}

        result = _handle_system_tools("get_docker_disk_usage", {"verbose": False})

        assert result is not None
        assert result["type"] == "summary"

        data = result["data"]

        # Check all summaries show zero
        for item in data:
            assert item["total"] == 0
            assert item["active"] == 0
            if item["type"] != "Build Cache":  # Build cache size starts at 0
                assert item["size"] == 0

    def test_get_docker_disk_usage_missing_fields(
        self,
        mock_docker_client: Mock,
        mock_docker_api_client: Mock,
    ) -> None:
        """Test Docker disk usage handling missing fields gracefully."""
        # Mock data with missing fields
        mock_images_data = [
            {
                "Id": "sha256:image1",
                # Missing Size, VirtualSize, RepoTags, Created
            },
        ]
        mock_docker_api_client.images.return_value = mock_images_data

        mock_containers_data = [
            {
                "Id": "container1",
                # Missing most fields
            }
        ]
        mock_docker_api_client.containers.return_value = mock_containers_data

        mock_docker_api_client.volumes.return_value = {"Volumes": [{}]}

        result = _handle_system_tools("get_docker_disk_usage", {"verbose": False})

        assert result is not None
        assert result["type"] == "summary"
        # Should not crash and return valid data structure

    def test_get_container_stats_running_containers(
        self, mock_docker_client: Mock
    ) -> None:
        """Test getting stats for all running containers."""
        # Mock container
        mock_container = Mock()
        mock_container.short_id = "abc123456789"
        mock_container.name = "test_container"

        # Mock stats data (similar to what Docker SDK returns)
        mock_stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 2000000000},
                "system_cpu_usage": 100000000000,
                "online_cpus": 2,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 1000000000},
                "system_cpu_usage": 99000000000,
            },
            "memory_stats": {"usage": 157286400, "limit": 8589934592},  # ~150MB  # ~8GB
            "networks": {"eth0": {"rx_bytes": 1024, "tx_bytes": 2048}},
            "blkio_stats": {
                "io_service_bytes_recursive": [
                    {"op": "Read", "value": 4096},
                    {"op": "Write", "value": 8192},
                ]
            },
            "pids_stats": {"current": 15},
        }

        mock_container.stats.return_value = mock_stats
        mock_docker_client.containers.list.return_value = [mock_container]

        result = _handle_system_tools("get_container_stats", {"all": False})

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 1

        stats = result[0]
        assert stats["container_id"] == "abc123456789"
        assert stats["name"] == "test_container"
        assert "cpu_percent" in stats
        assert stats["cpu_percent"].endswith("%")
        assert "memory_usage_limit" in stats
        assert stats["memory_percent"].endswith("%")
        assert "net_io" in stats
        assert "block_io" in stats
        assert stats["pids"] == "15"
        assert "raw_stats" in stats

        # Verify Docker client calls
        mock_docker_client.containers.list.assert_called_once_with(all=False)
        mock_container.stats.assert_called_once_with(stream=False)

    def test_get_container_stats_specific_containers(
        self, mock_docker_client: Mock
    ) -> None:
        """Test getting stats for specific containers by ID/name."""
        # Mock containers
        mock_container1 = Mock()
        mock_container1.short_id = "abc123"
        mock_container1.name = "container1"

        mock_container2 = Mock()
        mock_container2.short_id = "def456"
        mock_container2.name = "container2"

        # Mock stats
        mock_stats = {
            "cpu_stats": {
                "cpu_usage": {"total_usage": 1000},
                "system_cpu_usage": 10000,
            },
            "precpu_stats": {
                "cpu_usage": {"total_usage": 500},
                "system_cpu_usage": 9000,
            },
            "memory_stats": {"usage": 1048576, "limit": 2097152},
            "networks": {},
            "blkio_stats": {"io_service_bytes_recursive": []},
            "pids_stats": {"current": 5},
        }

        mock_container1.stats.return_value = mock_stats
        mock_container2.stats.return_value = mock_stats

        def mock_get(container_id: str) -> Mock:
            if container_id == "container1":
                return mock_container1
            elif container_id == "def456":
                return mock_container2
            else:
                raise Exception(f"Container {container_id} not found")

        mock_docker_client.containers.get.side_effect = mock_get

        result = _handle_system_tools(
            "get_container_stats",
            {"containers": ["container1", "def456"], "all": False},
        )

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 2

        # Check both containers are present
        container_names = [stats["name"] for stats in result]
        assert "container1" in container_names
        assert "container2" in container_names

        # Verify Docker client calls
        assert mock_docker_client.containers.get.call_count == 2

    def test_get_container_stats_all_containers(self, mock_docker_client: Mock) -> None:
        """Test getting stats for all containers including stopped ones."""
        # Mock running container
        mock_running = Mock()
        mock_running.short_id = "running123"
        mock_running.name = "running_container"

        # Mock stopped container
        mock_stopped = Mock()
        mock_stopped.short_id = "stopped123"
        mock_stopped.name = "stopped_container"

        mock_stats = {
            "cpu_stats": {"cpu_usage": {"total_usage": 0}, "system_cpu_usage": 1000},
            "precpu_stats": {"cpu_usage": {"total_usage": 0}, "system_cpu_usage": 900},
            "memory_stats": {"usage": 0, "limit": 1000000},
            "networks": {},
            "blkio_stats": {"io_service_bytes_recursive": []},
            "pids_stats": {"current": 0},
        }

        mock_running.stats.return_value = mock_stats
        mock_stopped.stats.return_value = mock_stats

        mock_docker_client.containers.list.return_value = [mock_running, mock_stopped]

        result = _handle_system_tools("get_container_stats", {"all": True})

        assert result is not None
        assert isinstance(result, list)
        assert len(result) == 2

        # Verify Docker client calls
        mock_docker_client.containers.list.assert_called_once_with(all=True)

    def test_get_container_stats_missing_container(
        self, mock_docker_client: Mock
    ) -> None:
        """Test handling of missing containers."""
        mock_docker_client.containers.get.side_effect = Exception("Container not found")

        result = _handle_system_tools(
            "get_container_stats", {"containers": ["nonexistent"], "all": False}
        )

        assert result == []  # Should return empty list when no containers found

    def test_get_container_stats_empty_list(self, mock_docker_client: Mock) -> None:
        """Test handling when no containers are running."""
        mock_docker_client.containers.list.return_value = []

        result = _handle_system_tools("get_container_stats", {"all": False})

        assert result == []

    def test_get_container_stats_stats_error(self, mock_docker_client: Mock) -> None:
        """Test handling when stats collection fails for a container."""
        mock_container = Mock()
        mock_container.short_id = "error123"
        mock_container.name = "error_container"
        mock_container.stats.side_effect = Exception("Stats collection failed")

        mock_docker_client.containers.list.return_value = [mock_container]

        result = _handle_system_tools("get_container_stats", {"all": False})

        assert result is not None
        assert len(result) == 1
        assert result[0]["name"] == "error_container"
        assert result[0]["cpu_percent"] == "N/A"
        assert "error" in result[0]

    def test_get_container_stats_malformed_stats(
        self, mock_docker_client: Mock
    ) -> None:
        """Test handling of malformed or incomplete stats data."""
        mock_container = Mock()
        mock_container.short_id = "malformed123"
        mock_container.name = "malformed_container"

        # Malformed stats (missing required fields)
        malformed_stats = {"some_random_field": "value"}
        mock_container.stats.return_value = malformed_stats

        mock_docker_client.containers.list.return_value = [mock_container]

        result = _handle_system_tools("get_container_stats", {"all": False})

        assert result is not None
        assert len(result) == 1

        stats = result[0]
        assert stats["name"] == "malformed_container"
        assert stats["cpu_percent"] == "0.00%"  # Should default to 0
        assert stats["memory_percent"] == "0.00%"

    def test_unknown_system_tool(self) -> None:
        """Test handling of unknown system tool."""
        result = _handle_system_tools("unknown_tool", {})
        assert result is None
