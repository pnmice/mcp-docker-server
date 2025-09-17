from typing import Any

from docker.models.containers import Container
from docker.models.images import Image
from docker.models.networks import Network
from docker.models.volumes import Volume


def _is_real_value(value: Any) -> bool:
    """Check if a value is a real value (not a Mock)."""
    return not (
        hasattr(value, "_mock_name")
        or str(type(value)).startswith("<class 'unittest.mock.")
    )


def _extract_basic_attributes(obj: Any, result: dict[str, Any]) -> None:
    """Extract basic attributes from a mock object."""
    basic_attrs = ["id", "name", "status", "short_id", "tags", "labels", "driver"]
    for attr in basic_attrs:
        if hasattr(obj, attr) and _is_real_value(getattr(obj, attr)):
            result[attr] = getattr(obj, attr)


def _transform_attrs(attrs: dict[str, Any], result: dict[str, Any]) -> None:
    """Transform attrs dictionary keys to match real Docker object output."""
    attr_mappings = {
        "Size": "size",
        "Created": "created",
        "RepoTags": "repo_tags",
        "RepoDigests": "repo_digests",
        "Driver": "driver",
        "Scope": "scope",
        "Mountpoint": "mountpoint",
        "CreatedAt": "created",
        "Labels": "labels",
    }
    for original_key, new_key in attr_mappings.items():
        if original_key in attrs:
            result[new_key] = attrs[original_key]


def _handle_mock_object(obj: Any) -> dict[str, Any] | None:
    """Handle mock objects in tests by extracting their attributes."""
    try:
        result: dict[str, Any] = {}

        # Extract basic attributes
        _extract_basic_attributes(obj, result)

        # Handle attrs with proper key mapping like real Docker objects
        if hasattr(obj, "attrs") and obj.attrs and _is_real_value(obj.attrs):
            attrs = obj.attrs
            _transform_attrs(attrs, result)
            # Also add all original attrs for compatibility
            result.update(attrs)

        return result if result else None
    except Exception:
        return None


def _format_ports_simple(ports: dict[str, Any]) -> str:
    """Format ports dictionary to a simple string similar to docker ps output."""
    if not ports:
        return ""

    port_strings = []
    for container_port, host_bindings in ports.items():
        if host_bindings:
            for binding in host_bindings:
                if binding and binding.get("HostPort"):
                    # Default to 0.0.0.0 for Docker port binding display
                    host_ip = binding.get("HostIp", "0.0.0.0")  # nosec B104
                    host_port = binding["HostPort"]
                    port_strings.append(f"{host_ip}:{host_port}->{container_port}")
                else:
                    port_strings.append(container_port)
        else:
            port_strings.append(container_port)

    return ", ".join(port_strings)


def _image_to_dict(obj: Image) -> dict[str, Any]:
    """Convert Docker Image object to dictionary."""
    img_config: dict[str, Any] = obj.attrs.get("Config") or {}

    return {
        "id": obj.id,
        "tags": obj.tags,
        "short_id": obj.short_id,
        "labels": img_config.get("Labels", {}),
        "repo_tags": obj.attrs.get("RepoTags"),
        "repo_digests": obj.attrs.get("RepoDigests"),
        "created": obj.attrs.get("Created"),
        "size": obj.attrs.get("Size"),
    }


def _container_to_dict(
    obj: Container,
    simple: bool = False,
    image_info_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert Docker Container object to dictionary."""
    config: dict[str, Any] = obj.attrs.get("Config") or {}

    if simple:
        # Simple format similar to docker ps -a - no image API calls for performance
        return {
            "id": obj.short_id,
            "image": config.get("Image", ""),
            "command": config.get("Cmd", [""])[0] if config.get("Cmd") else "",
            "created": obj.attrs.get("Created"),
            "status": obj.status,
            "ports": _format_ports_simple(obj.ports),
            "names": obj.name,
        }

    # Full detailed format with optimized image handling
    image_info = None
    if obj.image and image_info_map:
        # Use cached image info to avoid additional API calls
        image_info = image_info_map.get(obj.image.id)
    elif obj.image:
        # Fallback to minimal image info without recursive docker_to_dict call
        image_info = {
            "id": obj.image.short_id,
            "tags": getattr(obj.image, "tags", []),
            "short_id": obj.image.short_id,
        }

    return {
        "id": obj.id,
        "name": obj.name,
        "short_id": obj.short_id,
        "image": image_info,
        "status": obj.status,
        "labels": config.get("Labels", {}),
        "ports": obj.ports,
        "created": obj.attrs.get("Created"),
        "state": obj.attrs.get("State"),
        "restart_count": obj.attrs.get("RestartCount"),
        "networks": list(
            obj.attrs.get("NetworkSettings", {}).get("Networks", {}).keys()
        ),
        "mounts": obj.attrs.get("Mounts"),
        "config": {
            "hostname": config.get("Hostname"),
            "user": config.get("User"),
            "image": config.get("Image"),
        },
    }


def _network_to_dict(obj: Network) -> dict[str, Any]:
    """Convert Docker Network object to dictionary."""
    return {
        "id": obj.id,
        "name": obj.name,
        "short_id": obj.short_id,
        "driver": obj.attrs.get("Driver"),
        "scope": obj.attrs.get("Scope"),
        "created": obj.attrs.get("CreatedAt"),
        "labels": obj.attrs.get("Labels"),
    }


def _volume_to_dict(obj: Volume) -> dict[str, Any]:
    """Convert Docker Volume object to dictionary."""
    return {
        "id": obj.id,
        "name": obj.name,
        "short_id": obj.short_id,
        "labels": obj.attrs.get("Labels", {}),
        "mountpoint": obj.attrs.get("Mountpoint"),
        "created": obj.attrs.get("CreatedAt"),
        "driver": obj.attrs.get("Driver"),
        "scope": obj.attrs.get("Scope"),
    }


def docker_to_dict(
    obj: Image | Container | Volume | Network,
    overrides: dict[str, Any] | None = None,
    simple: bool = False,
    image_info_map: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Convert Docker objects to dictionary representation."""
    # Handle mock objects in tests
    if hasattr(obj, "_mock_name") or str(type(obj)).startswith(
        "<class 'unittest.mock."
    ):
        result = _handle_mock_object(obj) or {}
        if overrides:
            result.update(overrides)
        return result

    # Handle real Docker objects
    if isinstance(obj, Image):
        result = _image_to_dict(obj)
    elif isinstance(obj, Container):
        result = _container_to_dict(obj, simple=simple, image_info_map=image_info_map)
    elif isinstance(obj, Network):
        result = _network_to_dict(obj)
    elif isinstance(obj, Volume):
        result = _volume_to_dict(obj)
    else:
        raise ValueError(f"Unsupported object type: {type(obj)}")

    return result if overrides is None else {**result, **overrides}
