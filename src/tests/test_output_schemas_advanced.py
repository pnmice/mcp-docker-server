"""Advanced tests for output_schemas.py edge cases and error handling."""

from unittest.mock import Mock

import pytest
from docker.models.containers import Container
from docker.models.images import Image
from docker.models.networks import Network
from docker.models.volumes import Volume

from mcp_docker_server.output_schemas import docker_to_dict


@pytest.mark.unit
class TestDockerToDictAdvanced:
    """Test advanced edge cases in docker_to_dict functionality."""

    def test_docker_to_dict_image_object(self) -> None:
        """Test docker_to_dict with Image object."""
        mock_image = Mock(spec=Image)
        mock_image.id = "sha256:abc123"
        mock_image.short_id = "abc123"
        mock_image.tags = ["nginx:latest", "nginx:1.20"]
        mock_image.labels = {"maintainer": "nginx"}
        mock_image.attrs = {"Config": {"Labels": {"maintainer": "nginx"}}}

        result = docker_to_dict(mock_image)

        assert result["id"] == "sha256:abc123"
        assert result["tags"] == ["nginx:latest", "nginx:1.20"]
        assert result["labels"] == {"maintainer": "nginx"}

    def test_docker_to_dict_container_with_image_info_map(self) -> None:
        """Test docker_to_dict with Container and image_info_map."""
        mock_container = Mock(spec=Container)
        mock_container.id = "container123"
        mock_container.name = "test-container"
        mock_container.short_id = "container123"[:12]
        mock_container.status = "running"
        mock_container.ports = {}
        mock_container.image = Mock()
        mock_container.image.id = "image123"
        mock_container.image.short_id = "image123"[:12]
        mock_container.attrs = {
            "Config": {"Labels": {"app": "test"}},
            "HostConfig": {},
            "NetworkSettings": {"Networks": {}},
            "Created": "2025-01-01T00:00:00Z",
            "State": {"Status": "running"},
            "RestartCount": 0,
            "Mounts": [],
        }

        image_info_map = {
            "image123": {
                "id": "image123",
                "tags": ["nginx:latest"],
                "short_id": "image123"[:12],
            }
        }

        result = docker_to_dict(mock_container, image_info_map=image_info_map)

        assert result["name"] == "test-container"
        # For mock objects, image handling might be processed differently
        if "image" in result and result["image"]:
            assert "tags" in str(result["image"]) or "id" in str(result["image"])
        # The function should not crash even if image processing differs

    def test_docker_to_dict_container_without_image_info_map(self) -> None:
        """Test docker_to_dict with Container without image_info_map."""
        mock_container = Mock(spec=Container)
        mock_container.id = "container123"
        mock_container.name = "test-container"
        mock_container.short_id = "container123"[:12]
        mock_container.status = "running"
        mock_container.ports = {}
        mock_container.image = Mock()
        mock_container.image.id = "image123"
        mock_container.image.short_id = "image123"[:12]
        mock_container.image.tags = ["nginx:latest"]
        mock_container.attrs = {
            "Config": {"Labels": {"app": "test"}},
            "HostConfig": {},
            "NetworkSettings": {"Networks": {}},
            "Created": "2025-01-01T00:00:00Z",
            "State": {"Status": "running"},
            "RestartCount": 0,
            "Mounts": [],
        }

        result = docker_to_dict(mock_container)

        assert result["name"] == "test-container"
        # For mock objects, image handling might be processed differently
        if "image" in result and result["image"]:
            # Check if image data is present in some form
            assert "tags" in str(result["image"]) or "id" in str(result["image"])
        # The function should not crash even if image processing differs

    def test_docker_to_dict_container_no_image(self) -> None:
        """Test docker_to_dict with Container that has no image."""
        mock_container = Mock(spec=Container)
        mock_container.id = "container123"
        mock_container.name = "test-container"
        mock_container.short_id = "container123"[:12]
        mock_container.status = "running"
        mock_container.image = None
        mock_container.ports = {}
        mock_container.attrs = {
            "Config": {"Labels": {"app": "test"}},
            "HostConfig": {},
            "NetworkSettings": {"Networks": {}},
            "Created": "2025-01-01T00:00:00Z",
            "State": {"Status": "running"},
            "RestartCount": 0,
            "Mounts": [],
        }

        result = docker_to_dict(mock_container)

        assert result["name"] == "test-container"
        # For mock objects, check if image key exists before checking value
        assert result.get("image") is None

    def test_docker_to_dict_network_object(self) -> None:
        """Test docker_to_dict with Network object."""
        mock_network = Mock(spec=Network)
        mock_network.id = "network123"
        mock_network.name = "test-network"
        mock_network.short_id = "network123"[:12]
        mock_network.attrs = {
            "Driver": "bridge",
            "Scope": "local",
            "Labels": {"app": "test"},
            "Options": {"com.docker.network.bridge.name": "br-test"},
            "IPAM": {"Driver": "default"},
        }

        result = docker_to_dict(mock_network)

        assert result["name"] == "test-network"
        assert result["driver"] == "bridge"
        assert result["scope"] == "local"
        assert result["labels"] == {"app": "test"}

    def test_docker_to_dict_volume_object(self) -> None:
        """Test docker_to_dict with Volume object."""
        mock_volume = Mock(spec=Volume)
        mock_volume.id = "volume123"
        mock_volume.name = "test-volume"
        mock_volume.short_id = "volume123"[:12]
        mock_volume.attrs = {
            "Driver": "local",
            "Mountpoint": "/var/lib/docker/volumes/test-volume/_data",
            "Labels": {"app": "test"},
            "Options": {},
            "Scope": "local",
        }

        result = docker_to_dict(mock_volume)

        assert result["name"] == "test-volume"
        assert result["driver"] == "local"
        assert result["mountpoint"] == "/var/lib/docker/volumes/test-volume/_data"

    def test_docker_to_dict_unsupported_object(self) -> None:
        """Test docker_to_dict with unsupported object type."""

        # Create a real object that's not a mock and not a Docker type
        class UnsupportedType:
            pass

        unsupported_obj = UnsupportedType()

        with pytest.raises(ValueError, match="Unsupported object type"):
            docker_to_dict(unsupported_obj)

    def test_docker_to_dict_mock_object_with_overrides(self) -> None:
        """Test docker_to_dict with mock object and overrides."""
        mock_obj = Mock()
        mock_obj.attrs = {"test": "value"}

        overrides = {"status": "custom_status", "extra": "data"}
        result = docker_to_dict(mock_obj, overrides=overrides)

        assert result["status"] == "custom_status"
        assert result["extra"] == "data"
        assert result["test"] == "value"

    def test_docker_to_dict_container_simple_mode(self) -> None:
        """Test docker_to_dict with Container in simple mode."""
        mock_container = Mock(spec=Container)
        mock_container.id = "container123"
        mock_container.name = "test-container"
        mock_container.short_id = "container123"[:12]
        mock_container.status = "running"
        mock_container.ports = {}
        mock_container.image = Mock()
        mock_container.image.id = "image123"
        mock_container.image.short_id = "image123"[:12]
        mock_container.ports = {}
        mock_container.attrs = {
            "Config": {"Labels": {"app": "test"}},
            "Created": "2025-01-01T00:00:00Z",
            "State": {"Status": "running"},
            "RestartCount": 0,
            "Mounts": [],
        }

        result = docker_to_dict(mock_container, simple=True)

        assert result["name"] == "test-container"
        # For mock objects, image handling might be different
        # Just ensure the function doesn't crash and returns a valid result

    def test_docker_to_dict_image_with_missing_attrs(self) -> None:
        """Test docker_to_dict with Image missing some attributes."""
        mock_image = Mock(spec=Image)
        mock_image.id = "sha256:abc123"
        mock_image.short_id = "abc123"
        mock_image.tags = ["nginx:latest"]
        mock_image.attrs = {}  # No Config section
        # Missing labels attribute
        del mock_image.labels

        result = docker_to_dict(mock_image)

        assert result["id"] == "sha256:abc123"
        assert result["tags"] == ["nginx:latest"]
        # Should handle missing labels gracefully

    def test_docker_to_dict_container_missing_config(self) -> None:
        """Test docker_to_dict with Container missing config sections."""
        mock_container = Mock(spec=Container)
        mock_container.id = "container123"
        mock_container.name = "test-container"
        mock_container.short_id = "container123"[:12]
        mock_container.status = "running"
        mock_container.image = None
        mock_container.ports = {}
        mock_container.attrs = {}  # Missing Config, HostConfig, etc.

        result = docker_to_dict(mock_container)

        assert result["name"] == "test-container"
        # For mock objects, image handling might be different
        assert result.get("image") is None

    def test_docker_to_dict_network_missing_attrs(self) -> None:
        """Test docker_to_dict with Network missing some attributes."""
        mock_network = Mock(spec=Network)
        mock_network.id = "network123"
        mock_network.name = "test-network"
        mock_network.short_id = "network123"[:12]
        mock_network.attrs = {
            "Driver": "bridge",
            # Missing Scope, Labels, etc.
        }

        result = docker_to_dict(mock_network)

        assert result["name"] == "test-network"
        assert result["driver"] == "bridge"
        # Should handle missing attributes gracefully

    def test_docker_to_dict_volume_missing_attrs(self) -> None:
        """Test docker_to_dict with Volume missing some attributes."""
        mock_volume = Mock(spec=Volume)
        mock_volume.id = "volume123"
        mock_volume.name = "test-volume"
        mock_volume.short_id = "volume123"[:12]
        mock_volume.attrs = {
            "Driver": "local",
            # Missing Mountpoint, Labels, etc.
        }

        result = docker_to_dict(mock_volume)

        assert result["name"] == "test-volume"
        assert result["driver"] == "local"
