"""
Tests for input and output schemas.
"""

from typing import Any
from unittest.mock import Mock

import pytest
from pydantic import ValidationError

from mcp_docker_server.input_schemas import (
    BuildImageInput,
    ContainerActionInput,
    CreateContainerInput,
    CreateNetworkInput,
    CreateVolumeInput,
    FetchContainerLogsInput,
    ListContainersFilters,
    ListContainersInput,
    ListImagesFilters,
    ListImagesInput,
    ListNetworksFilter,
    ListNetworksInput,
    ListVolumesInput,
    PullPushImageInput,
    RecreateContainerInput,
    RemoveContainerInput,
    RemoveImageInput,
    RemoveNetworkInput,
    RemoveVolumeInput,
)
from mcp_docker_server.output_schemas import docker_to_dict


@pytest.mark.unit
class TestInputSchemas:
    """Test input schema validation."""

    def test_list_containers_input_valid(self) -> None:
        """Test valid ListContainersInput."""
        filters = ListContainersFilters(
            label=["test=value"], status=None, name=None, id=None, ancestor=None
        )
        schema = ListContainersInput(all=True, filters=filters, limit=None)
        assert schema.all is True
        assert schema.filters is not None
        assert schema.filters.label == ["test=value"]

    def test_list_containers_input_defaults(self) -> None:
        """Test ListContainersInput with defaults."""
        schema = ListContainersInput()  # type: ignore[call-arg]
        assert schema.all is False
        assert schema.filters is None

    def test_create_container_input_valid(self) -> None:
        """Test valid CreateContainerInput."""
        schema = CreateContainerInput(  # type: ignore[call-arg]
            image="nginx:latest",
            name="test-nginx",
            command="nginx -g 'daemon off;'",
            ports={"80/tcp": 8080},
            environment={"ENV": "test"},
            volumes=["/host:/container"],
            detach=True,
            auto_remove=False,
        )
        assert schema.image == "nginx:latest"
        assert schema.name == "test-nginx"
        assert schema.ports == {"80/tcp": 8080}
        assert schema.environment == {"ENV": "test"}
        assert schema.detach is True

    def test_create_container_input_required_image(self) -> None:
        """Test CreateContainerInput requires image."""
        with pytest.raises(ValidationError, match="Field required"):
            CreateContainerInput()  # type: ignore[call-arg]

    def test_container_action_input_valid(self) -> None:
        """Test valid ContainerActionInput."""
        schema = ContainerActionInput(container_id="test_container")
        assert schema.container_id == "test_container"

    def test_recreate_container_input_valid(self) -> None:
        """Test valid RecreateContainerInput."""
        schema = RecreateContainerInput(  # type: ignore[call-arg]
            image="nginx:latest", container_id="old_container", name="new_container"
        )
        assert schema.image == "nginx:latest"
        assert schema.container_id == "old_container"
        assert schema.resolved_container_id == "old_container"  # type: ignore[comparison-overlap]

    def test_recreate_container_input_name_fallback(self) -> None:
        """Test RecreateContainerInput falls back to name."""
        schema = RecreateContainerInput(image="nginx:latest", name="container_name")  # type: ignore[call-arg]
        assert schema.resolved_container_id == "container_name"  # type: ignore[comparison-overlap]

    def test_remove_container_input_valid(self) -> None:
        """Test valid RemoveContainerInput."""
        schema = RemoveContainerInput(container_id="test", force=True)
        assert schema.container_id == "test"
        assert schema.force is True

    def test_fetch_container_logs_input_valid(self) -> None:
        """Test valid FetchContainerLogsInput."""
        schema = FetchContainerLogsInput(container_id="test", tail=50)
        assert schema.container_id == "test"
        assert schema.tail == 50

    def test_fetch_container_logs_input_default_tail(self) -> None:
        """Test FetchContainerLogsInput default tail."""
        schema = FetchContainerLogsInput(container_id="test")  # type: ignore[call-arg]
        assert schema.tail == 100

    def test_list_images_input_valid(self) -> None:
        """Test valid ListImagesInput."""
        filters = ListImagesFilters(dangling=True)  # type: ignore[call-arg]
        schema = ListImagesInput(all=True, name="nginx", filters=filters)
        assert schema.all is True
        assert schema.name == "nginx"
        assert schema.filters is not None
        assert schema.filters.dangling is True

    def test_pull_push_image_input_valid(self) -> None:
        """Test valid PullPushImageInput."""
        schema = PullPushImageInput(repository="nginx", tag="1.20")
        assert schema.repository == "nginx"
        assert schema.tag == "1.20"

    def test_pull_push_image_input_default_tag(self) -> None:
        """Test PullPushImageInput default tag."""
        schema = PullPushImageInput(repository="nginx")  # type: ignore[call-arg]
        assert schema.tag == "latest"

    def test_build_image_input_valid(self) -> None:
        """Test valid BuildImageInput."""
        schema = BuildImageInput(
            path="/tmp/build", tag="myapp:latest", dockerfile="Dockerfile"
        )
        assert schema.path == "/tmp/build"
        assert schema.tag == "myapp:latest"
        assert schema.dockerfile == "Dockerfile"

    def test_remove_image_input_valid(self) -> None:
        """Test valid RemoveImageInput."""
        schema = RemoveImageInput(image="nginx:latest", force=True)
        assert schema.image == "nginx:latest"
        assert schema.force is True

    def test_list_networks_input_valid(self) -> None:
        """Test valid ListNetworksInput."""
        filters = ListNetworksFilter(label=["env=test"])
        schema = ListNetworksInput(filters=filters)
        assert schema.filters is not None
        assert schema.filters.label == ["env=test"]

    def test_create_network_input_valid(self) -> None:
        """Test valid CreateNetworkInput."""
        schema = CreateNetworkInput(
            name="test-network", driver="overlay", internal=True, labels={"env": "test"}
        )
        assert schema.name == "test-network"
        assert schema.driver == "overlay"
        assert schema.internal is True
        assert schema.labels == {"env": "test"}

    def test_create_network_input_default_driver(self) -> None:
        """Test CreateNetworkInput default driver."""
        schema = CreateNetworkInput(name="test-network")  # type: ignore[call-arg]
        assert schema.driver == "bridge"

    def test_remove_network_input_valid(self) -> None:
        """Test valid RemoveNetworkInput."""
        schema = RemoveNetworkInput(network_id="network123")
        assert schema.network_id == "network123"

    def test_list_volumes_input_valid(self) -> None:
        """Test valid ListVolumesInput."""
        schema = ListVolumesInput()
        # This schema is empty, just test it validates
        assert isinstance(schema, ListVolumesInput)

    def test_create_volume_input_valid(self) -> None:
        """Test valid CreateVolumeInput."""
        schema = CreateVolumeInput(
            name="test-volume", driver="nfs", labels={"env": "test"}
        )
        assert schema.name == "test-volume"
        assert schema.driver == "nfs"
        assert schema.labels == {"env": "test"}

    def test_create_volume_input_default_driver(self) -> None:
        """Test CreateVolumeInput default driver."""
        schema = CreateVolumeInput(name="test-volume")  # type: ignore[call-arg]
        assert schema.driver == "local"

    def test_remove_volume_input_valid(self) -> None:
        """Test valid RemoveVolumeInput."""
        schema = RemoveVolumeInput(volume_name="test-volume", force=True)
        assert schema.volume_name == "test-volume"
        assert schema.force is True


@pytest.mark.unit
class TestOutputSchemas:
    """Test output schema functions."""

    def test_docker_to_dict_container(self, mock_container: Mock) -> None:
        """Test docker_to_dict with container."""
        result = docker_to_dict(mock_container)

        assert isinstance(result, dict)
        assert result["id"] == "test_container_id"
        assert result["name"] == "/test_container"
        assert result["status"] == "running"
        # For mock objects, attrs are merged into the result
        assert result["Id"] == "test_container_id"
        assert result["Name"] == "/test_container"
        assert result["Config"]["Image"] == "test:latest"

    def test_docker_to_dict_container_with_overrides(
        self, mock_container: Mock
    ) -> None:
        """Test docker_to_dict with overrides."""
        overrides = {"status": "stopped", "custom_field": "value"}
        result = docker_to_dict(mock_container, overrides)

        assert result["status"] == "stopped"
        assert result["custom_field"] == "value"
        assert result["id"] == "test_container_id"  # Original data preserved

    def test_docker_to_dict_image(self, mock_image: Mock) -> None:
        """Test docker_to_dict with image."""
        result = docker_to_dict(mock_image)

        assert isinstance(result, dict)
        assert result["id"] == "test_image_id"
        assert result["short_id"] == "test_image_short"
        assert result["tags"] == ["test:latest"]
        assert result["size"] == 1000000

    def test_docker_to_dict_network(self, mock_network: Mock) -> None:
        """Test docker_to_dict with network."""
        result = docker_to_dict(mock_network)

        assert isinstance(result, dict)
        assert result["id"] == "test_network_id"
        assert result["name"] == "test_network"
        assert result["driver"] == "bridge"

    def test_docker_to_dict_volume(self, mock_volume: Mock) -> None:
        """Test docker_to_dict with volume."""
        result = docker_to_dict(mock_volume)

        assert isinstance(result, dict)
        assert result["name"] == "test_volume"
        assert result["driver"] == "local"
        assert result["mountpoint"] == "/var/lib/docker/volumes/test_volume/_data"

    def test_docker_to_dict_none_attrs(self) -> None:
        """Test docker_to_dict with object that has no attrs."""
        mock_obj = Mock()
        del mock_obj.attrs  # Remove attrs attribute

        result = docker_to_dict(mock_obj)
        assert result == {}

    def test_docker_to_dict_exception_handling(self) -> None:
        """Test docker_to_dict handles exceptions gracefully."""
        mock_obj = Mock()
        mock_obj.attrs = {"key": "value"}
        # Make accessing attrs raise an exception
        type(mock_obj).attrs = property(
            lambda self: (_ for _ in ()).throw(Exception("Test error"))
        )

        result = docker_to_dict(mock_obj)
        assert result == {}  # Should return empty dict on error

    def test_docker_to_dict_container_simple_format(self) -> None:
        """Test _container_to_dict with container in simple format (docker ps -a like)."""
        from mcp_docker_server.output_schemas import _container_to_dict

        # Create a mock container that won't trigger mock object detection
        mock_container = Mock()
        mock_container.short_id = "abc123456789"
        mock_container.status = "running"
        mock_container.name = "/test-container"
        mock_container.ports = {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}
        mock_container.attrs = {
            "Created": "2025-09-16T19:26:21.553367722Z",
            "Config": {"Image": "nginx:latest", "Cmd": ["nginx", "-g", "daemon off;"]},
        }

        # Test simple format directly
        result = _container_to_dict(mock_container, simple=True)

        # Verify simple format matches docker ps -a structure
        expected_keys = {
            "id",
            "image",
            "command",
            "created",
            "status",
            "ports",
            "names",
        }
        assert set(result.keys()) == expected_keys

        # Verify values match expected simple format
        assert result["id"] == "abc123456789"  # short_id instead of full id
        assert result["image"] == "nginx:latest"  # image name from config
        assert result["status"] == "running"
        assert result["names"] == "/test-container"
        assert result["command"] == "nginx"  # first command element
        assert result["ports"] == "0.0.0.0:8080->80/tcp"
        assert result["created"] == "2025-09-16T19:26:21.553367722Z"

    def test_docker_to_dict_container_full_format(self) -> None:
        """Test _container_to_dict with container in full format (default)."""
        from mcp_docker_server.output_schemas import _container_to_dict

        # Create a mock container for full format testing
        mock_container = Mock()
        mock_container.id = "test_container_id_full"
        mock_container.name = "/test_container_full"
        mock_container.short_id = "test_short_full"
        mock_container.status = "running"
        mock_container.ports = {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}
        mock_container.image = Mock()
        mock_container.image.id = "image_id"
        mock_container.attrs = {
            "Created": "2025-09-16T19:26:21.553367722Z",
            "Config": {
                "Image": "nginx:latest",
                "Cmd": ["nginx", "-g", "daemon off;"],
                "Labels": {"app": "test"},
                "Hostname": "test-host",
                "User": "nginx",
            },
            "State": {"Status": "running", "Pid": 1234},
            "RestartCount": 0,
            "NetworkSettings": {"Networks": {"bridge": {}}},
            "Mounts": [{"Type": "volume", "Source": "/var/lib/docker/volumes"}],
        }

        result = _container_to_dict(mock_container, simple=False)

        # Verify full format has all detailed fields
        expected_keys = {
            "id",
            "name",
            "short_id",
            "image",
            "status",
            "labels",
            "ports",
            "created",
            "state",
            "restart_count",
            "networks",
            "mounts",
            "config",
        }
        assert set(result.keys()).issuperset(expected_keys)

        # Verify it has the detailed information
        assert result["id"] == "test_container_id_full"  # full id
        assert result["name"] == "/test_container_full"
        assert result["short_id"] == "test_short_full"
        assert "state" in result
        assert "mounts" in result
        assert "networks" in result
        assert result["state"]["Status"] == "running"

    def test_format_ports_simple_empty(self) -> None:
        """Test _format_ports_simple with empty ports."""
        from mcp_docker_server.output_schemas import _format_ports_simple

        result = _format_ports_simple({})
        assert result == ""

    def test_format_ports_simple_with_host_binding(self) -> None:
        """Test _format_ports_simple with host port binding."""
        from mcp_docker_server.output_schemas import _format_ports_simple

        ports = {
            "80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}],
            "443/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8443"}],
        }
        result = _format_ports_simple(ports)

        # Should format like docker ps output
        assert "0.0.0.0:8080->80/tcp" in result
        assert "127.0.0.1:8443->443/tcp" in result

    def test_format_ports_simple_without_host_binding(self) -> None:
        """Test _format_ports_simple with ports but no host binding."""
        from mcp_docker_server.output_schemas import _format_ports_simple

        ports: dict[str, Any] = {"80/tcp": None, "443/tcp": []}
        result = _format_ports_simple(ports)

        # Should just show the container ports
        assert "80/tcp" in result
        assert "443/tcp" in result

    def test_list_containers_simple_schema_compatibility(self) -> None:
        """Test that simple container format is compatible with docker ps -a output."""
        from mcp_docker_server.output_schemas import _container_to_dict

        # This test verifies the schema matches what docker ps -a would return
        expected_schema = {
            "id": str,  # CONTAINER ID (short)
            "image": str,  # IMAGE
            "command": str,  # COMMAND
            "created": str,  # CREATED AT
            "status": str,  # STATUS
            "ports": str,  # PORTS (formatted string)
            "names": str,  # NAMES
        }

        # Create a mock container to test the schema
        mock_container = Mock()
        mock_container.short_id = "abc123456789"
        mock_container.status = "running"
        mock_container.name = "/test-container"
        mock_container.ports = {"80/tcp": [{"HostIp": "0.0.0.0", "HostPort": "8080"}]}
        mock_container.attrs = {
            "Created": "2025-09-16T19:26:21.553367722Z",
            "Config": {"Image": "nginx:latest", "Cmd": ["nginx", "-g", "daemon off;"]},
        }

        result = _container_to_dict(mock_container, simple=True)

        # Verify all expected fields are present and have correct types
        for field, expected_type in expected_schema.items():
            assert field in result, f"Missing field: {field}"
            assert isinstance(
                result[field], expected_type
            ), f"Wrong type for {field}: expected {expected_type}, got {type(result[field])}"

        # Verify no extra fields that would increase token usage
        extra_fields = set(result.keys()) - set(expected_schema.keys())
        assert not extra_fields, f"Unexpected extra fields: {extra_fields}"
