"""Advanced tests for server.py functionality including filters and caching."""

from typing import Any
from unittest.mock import Mock, patch

import pytest

from mcp_docker_server.input_schemas import (
    ListContainersFilters,
    ListContainersInput,
    ListImagesFilters,
    ListImagesInput,
    ListNetworksFilter,
    ListNetworksInput,
)
from mcp_docker_server.server import (
    _batch_fetch_image_info,
    _cache_image_info,
    _convert_filters_to_docker_format,
    _get_cached_image_info,
    _handle_list_containers,
    _handle_list_images,
    _handle_list_networks,
    _handle_list_volumes,
)


@pytest.mark.unit
class TestFilterProcessing:
    """Test filter processing functionality."""

    def test_convert_filters_all_fields(self) -> None:
        """Test filter conversion with all fields populated."""
        filters = ListContainersFilters(
            label=["app=test", "env=prod"],
            status=["running", "exited"],
            name=["container1", "container2"],
            id=["abc123", "def456"],
            ancestor=["ubuntu:20.04", "nginx:latest"],
        )

        result = _convert_filters_to_docker_format(filters)

        assert result == {
            "label": ["app=test", "env=prod"],
            "status": ["running", "exited"],
            "name": ["container1", "container2"],
            "id": ["abc123", "def456"],
            "ancestor": ["ubuntu:20.04", "nginx:latest"],
        }

    def test_convert_filters_partial_fields(self) -> None:
        """Test filter conversion with only some fields."""
        filters = ListContainersFilters(
            label=["app=test"], status=["running"], name=None, id=None, ancestor=None
        )

        result = _convert_filters_to_docker_format(filters)

        assert result == {"label": ["app=test"], "status": ["running"]}

    def test_convert_filters_empty(self) -> None:
        """Test filter conversion with no fields."""
        filters = ListContainersFilters(
            label=None, status=None, name=None, id=None, ancestor=None
        )

        result = _convert_filters_to_docker_format(filters)

        assert result == {}


@pytest.mark.unit
class TestImageCaching:
    """Test image caching functionality."""

    def test_get_cached_image_info_exists(self) -> None:
        """Test getting cached image info that exists."""
        image_id = "test_image_123"
        test_info = {"id": "test", "tags": ["latest"]}

        # Mock the cache
        with patch("mcp_docker_server.server._image_cache", {image_id: test_info}):
            result = _get_cached_image_info(image_id)

        assert result == test_info

    def test_get_cached_image_info_not_exists(self) -> None:
        """Test getting cached image info that doesn't exist."""
        with patch("mcp_docker_server.server._image_cache", {}):
            result = _get_cached_image_info("nonexistent")

        assert result is None

    def test_cache_image_info_normal(self) -> None:
        """Test caching image info under normal conditions."""
        image_id = "test_image_123"
        test_info = {"id": "test", "tags": ["latest"]}

        mock_cache: dict[str, dict[str, Any]] = {}
        with patch("mcp_docker_server.server._image_cache", mock_cache):
            _cache_image_info(image_id, test_info)

        assert mock_cache[image_id] == test_info

    def test_cache_image_info_lru_eviction(self) -> None:
        """Test LRU eviction when cache is full."""
        # Fill cache to capacity
        initial_cache = {f"image_{i}": {"id": f"img_{i}"} for i in range(1000)}

        with patch("mcp_docker_server.server._CACHE_SIZE_LIMIT", 1000):
            with patch("mcp_docker_server.server._image_cache", initial_cache):
                # This should trigger eviction
                _cache_image_info("new_image", {"id": "new"})

        # Cache should be smaller after eviction
        assert len(initial_cache) < 1000

    def test_batch_fetch_image_info_all_cached(self) -> None:
        """Test batch fetch when all images are cached."""
        image_ids = {"img1", "img2", "img3"}
        cached_data = {
            "img1": {"id": "img1", "tags": ["v1"]},
            "img2": {"id": "img2", "tags": ["v2"]},
            "img3": {"id": "img3", "tags": ["v3"]},
        }

        with patch("mcp_docker_server.server._image_cache", cached_data):
            result = _batch_fetch_image_info(image_ids)

        assert result == cached_data

    @patch("mcp_docker_server.server._docker")
    def test_batch_fetch_image_info_uncached(self, mock_docker: Mock) -> None:
        """Test batch fetch when images are not cached."""
        image_ids = {"img1", "img2"}
        mock_images = [
            Mock(id="img1", short_id="img1_short", tags=["v1"]),
            Mock(id="img2", short_id="img2_short", tags=["v2"]),
        ]
        mock_docker.images.list.return_value = mock_images

        with patch("mcp_docker_server.server._image_cache", {}):
            result = _batch_fetch_image_info(image_ids)

        assert "img1" in result
        assert "img2" in result

    @patch("mcp_docker_server.server._docker")
    def test_batch_fetch_image_info_api_failure(self, mock_docker: Mock) -> None:
        """Test batch fetch when API fails."""
        image_ids = {"img1", "img2"}
        mock_docker.images.list.side_effect = Exception("API Error")

        with patch("mcp_docker_server.server._image_cache", {}):
            result = _batch_fetch_image_info(image_ids)

        # Should return minimal info for all images
        assert len(result) == 2
        assert all("id" in info for info in result.values())


@pytest.mark.unit
class TestAdvancedListOperations:
    """Test advanced functionality in list operations."""

    @patch("mcp_docker_server.server._docker_api")
    def test_list_containers_with_filters(self, mock_api: Mock) -> None:
        """Test list containers with complex filters."""
        mock_api.containers.return_value = [
            {
                "Id": "container123",
                "Names": ["/test-container"],
                "Image": "nginx:latest",
                "Command": ["nginx", "-g", "daemon off;"],
                "Created": 1694876781,
                "Status": "Up 1 hour",
                "Ports": [{"PrivatePort": 80, "Type": "tcp"}],
            }
        ]

        args = ListContainersInput(
            all=True,
            filters=ListContainersFilters(
                status=["running"],
                label=["app=test"],
                name=None,
                id=None,
                ancestor=None,
            ),
            limit=50,
        )

        result = _handle_list_containers(args)

        assert len(result) == 1
        assert result[0]["id"] == "container123"[:12]
        mock_api.containers.assert_called_once_with(
            all=True, filters={"status": ["running"], "label": ["app=test"]}
        )

    @patch("mcp_docker_server.server._docker_api")
    def test_list_images_with_filters(self, mock_api: Mock) -> None:
        """Test list images with filters."""
        mock_api.images.return_value = [
            {
                "Id": "sha256:image123",
                "RepoTags": ["nginx:latest"],
                "Created": 1694876781,
                "Size": 123456789,
                "VirtualSize": 123456789,
                "Labels": {"maintainer": "nginx"},
            }
        ]

        args = ListImagesInput(
            all=True,
            filters=ListImagesFilters(dangling=True, label=["maintainer=nginx"]),
            name="nginx",
        )

        result = _handle_list_images(args)

        assert len(result) == 1
        assert result[0]["id"] == "image123"
        mock_api.images.assert_called_once_with(
            all=True, filters={"dangling": ["true"], "label": ["maintainer=nginx"]}
        )

    @patch("mcp_docker_server.server._docker_api")
    def test_list_networks_with_filters(self, mock_api: Mock) -> None:
        """Test list networks with filters."""
        mock_api.networks.return_value = [
            {
                "Id": "network123",
                "Name": "test-network",
                "Driver": "bridge",
                "Scope": "local",
                "Created": "2025-01-01T12:00:00Z",
                "Labels": {"app": "test"},
                "Options": {},
                "IPAM": {"Driver": "default"},
            }
        ]

        args = ListNetworksInput(filters=ListNetworksFilter(label=["app=test"]))

        result = _handle_list_networks(args)

        assert len(result) == 1
        assert result[0]["name"] == "test-network"
        mock_api.networks.assert_called_once_with(filters={"label": ["app=test"]})

    @patch("mcp_docker_server.server._docker_api")
    def test_list_volumes_large_response(self, mock_api: Mock) -> None:
        """Test list volumes with large response."""
        # Create large volume list
        volumes = [
            {
                "Name": f"volume_{i}",
                "Driver": "local",
                "Mountpoint": f"/var/lib/docker/volumes/volume_{i}/_data",
                "CreatedAt": "2025-01-01T12:00:00Z",
                "Labels": {"index": str(i)},
                "Options": {},
                "Scope": "local",
            }
            for i in range(100)
        ]

        mock_api.volumes.return_value = {"Volumes": volumes}

        result = _handle_list_volumes()

        assert len(result) == 100
        assert result[0]["name"] == "volume_0"
        assert result[99]["name"] == "volume_99"


@pytest.mark.unit
class TestErrorHandling:
    """Test error handling in various scenarios."""

    @patch("mcp_docker_server.server._docker_api")
    def test_list_containers_api_error(self, mock_api: Mock) -> None:
        """Test handling of API errors in list containers."""
        mock_api.containers.side_effect = Exception("Docker daemon not running")

        args = ListContainersInput(all=False, filters=None, limit=100)

        with pytest.raises(Exception):
            _handle_list_containers(args)

    @patch("mcp_docker_server.server._docker_api")
    def test_list_images_empty_response(self, mock_api: Mock) -> None:
        """Test handling of empty API responses."""
        mock_api.images.return_value = []

        args = ListImagesInput(name=None, all=False, filters=None)
        result = _handle_list_images(args)

        assert result == []

    @patch("mcp_docker_server.server._docker_api")
    def test_list_volumes_none_response(self, mock_api: Mock) -> None:
        """Test handling of None API responses."""
        mock_api.volumes.return_value = None

        result = _handle_list_volumes()

        assert result == []

    @patch("mcp_docker_server.server._docker_api")
    def test_list_volumes_missing_volumes_key(self, mock_api: Mock) -> None:
        """Test handling of response missing Volumes key."""
        mock_api.volumes.return_value = {"Message": "No volumes found"}

        result = _handle_list_volumes()

        assert result == []
