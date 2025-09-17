import json
import logging
import os
import re
import sys
import time
import traceback
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from enum import Enum
from threading import Lock
from typing import Any

import docker
import mcp.types as types
from docker.api import APIClient
from docker.models.containers import Container
from mcp.server import Server
from pydantic import AnyUrl, ValidationError

from .input_schemas import (
    BuildImageInput,
    ContainerActionInput,
    CreateContainerInput,
    CreateNetworkInput,
    CreateVolumeInput,
    DockerComposePromptInput,
    FetchContainerLogsInput,
    GetContainerStatsInput,
    GetDockerDiskUsageInput,
    ListContainersFilters,
    ListContainersInput,
    ListImagesInput,
    ListNetworksInput,
    ListVolumesInput,
    PullPushImageInput,
    RecreateContainerInput,
    RemoveContainerInput,
    RemoveImageInput,
    RemoveNetworkInput,
    RemoveVolumeInput,
)
from .output_schemas import docker_to_dict
from .settings import ServerSettings

app: Server = Server("docker-server")
_docker: docker.DockerClient
_docker_api: APIClient
_server_settings: ServerSettings

# Performance optimization: Image cache
_image_cache: dict[str, dict[str, Any]] = {}
_image_cache_lock = Lock()
_CACHE_SIZE_LIMIT = 1000  # Limit cache to prevent memory bloat

# SSH Connection Management
_FAILURE_THRESHOLD = 10  # Stop stats collection after this many failures
_BATCH_SIZE = 5  # Process containers in batches to avoid SSH overload
_RETRY_DELAYS = [0.5, 1.0, 2.0, 4.0, 8.0]  # Exponential backoff delays

# Configure enhanced logging for real-time Docker output
logger = logging.getLogger(__name__)

# Configure logging to ensure real-time output in Docker containers
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s.%(msecs)03d [%(levelname)8s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    force=True,
    handlers=[logging.StreamHandler(sys.stdout)],
)

# Ensure all handlers flush immediately and configure line buffering
for handler in logging.root.handlers:
    if hasattr(handler, "flush"):
        original_flush = handler.flush

        def make_flusher(orig_flush: Callable) -> Callable:
            return lambda: (orig_flush(), sys.stdout.flush())[-1]

        # Store the enhanced flush function
        enhanced_flush = make_flusher(original_flush)
        setattr(handler, "flush", enhanced_flush)

# Force immediate flushing of stdout/stderr
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(line_buffering=True)
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(line_buffering=True)
except Exception:  # nosec B110 - fallback for reconfigure unavailability
    # Fallback for environments where reconfigure is not available
    # This is for compatibility across different Python environments
    pass


@app.list_prompts()  # type: ignore[misc]
async def list_prompts() -> list[types.Prompt]:
    return [
        types.Prompt(
            name="docker_compose",
            description="Treat the LLM like a Docker Compose manager",
            arguments=[
                types.PromptArgument(
                    name="name", description="Unique name of the project", required=True
                ),
                types.PromptArgument(
                    name="containers",
                    description="Describe containers you want",
                    required=True,
                ),
            ],
        )
    ]


@app.get_prompt()  # type: ignore[misc]
async def get_prompt(
    name: str, arguments: dict[str, str] | None
) -> types.GetPromptResult:
    if name == "docker_compose":
        input = DockerComposePromptInput.model_validate(arguments)
        project_label = f"mcp-docker-server.project={input.name}"
        containers: list[Container] = _docker.containers.list(
            filters={"label": project_label}
        )
        volumes = _docker.volumes.list(filters={"label": project_label})
        networks = _docker.networks.list(filters={"label": project_label})

        return types.GetPromptResult(
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=f"""
You are going to act as a Docker Compose manager, using the Docker Tools
available to you. Instead of being provided a `docker-compose.yml` file,
you will be given instructions in plain language, and interact with the
user through a plan+apply loop, akin to how Terraform operates.

Every Docker resource you create must be assigned the following label:

    {project_label}

You should use this label to filter resources when possible.

Every Docker resource you create must also be prefixed with the project name, followed by a dash (`-`):

    {input.name}-{{ResourceName}}

Here are the resources currently present in the project, based on the presence of the above label:

<BEGIN CONTAINERS>
{json.dumps([docker_to_dict(c) for c in containers], indent=2)}
<END CONTAINERS>
<BEGIN VOLUMES>
{json.dumps([docker_to_dict(v) for v in volumes], indent=2)}
<END VOLUMES>
<BEGIN NETWORKS>
{json.dumps([docker_to_dict(n) for n in networks], indent=2)}
<END NETWORKS>

Do not retry the same failed action more than once. Prefer terminating your output
when presented with 3 errors in a row, and ask a clarifying question to
form better inputs or address the error.

For container images, always prefer using the `latest` image tag, unless the user specifies a tag specifically.
So if a user asks to deploy Nginx, you should pull `nginx:latest`.

Below is a description of the state of the Docker resources which the user would like you to manage:

<BEGIN DOCKER-RESOURCES>
{input.containers}
<END DOCKER-RESOURCES>

Respond to this message with a plan of what you will do, in the EXACT format below:

<BEGIN FORMAT>
## Introduction

I will be assisting with deploying Docker containers for project: `{input.name}`.

### Plan+Apply Loop

I will run in a plan+apply loop when you request changes to the project. This is
to ensure that you are aware of the changes I am about to make, and to give you
the opportunity to ask questions or make tweaks.

Instruct me to apply immediately (without confirming the plan with you) when you desire to do so.

## Commands

Instruct me with the following commands at any point:

- `help`: print this list of commands
- `apply`: apply a given plan
- `down`: stop containers in the project
- `ps`: list containers in the project
- `quiet`: turn on quiet mode (default)
- `verbose`: turn on verbose mode (I will explain a lot!)
- `destroy`: produce a plan to destroy all resources in the project

## Plan

I plan to take the following actions:

1. CREATE ...
2. READ ...
3. UPDATE ...
4. DESTROY ...
5. RECREATE ...
...
N. ...

Respond `apply` to apply this plan. Otherwise, provide feedback and I will present you with an updated plan.
<END FORMAT>

Always apply a plan in dependency order. For example, if you are creating a container that depends on a
database, create the database first, and abort the apply if dependency creation fails. Likewise,
destruction should occur in the reverse dependency order, and be aborted if destroying a particular resource fails.

Plans should only create, update, or destroy resources in the project. Relatedly, "recreate" should
be used to indicate a destroy followed by a create; always prefer udpating a resource when possible,
only recreating it if required (e.g. for immutable resources like containers).

If the project already exists (as indicated by the presence of resources above) and your plan would
produce no changes, simply respond with "No changes to make; project is up-to-date." If the user requests
changes that would render a resource obsolete (e.g. an unused volume), you should destroy the resource.

If you produce a plan and the next user message is not `apply`, simply drop the plan and inform
the user that they must explicitly include "apply" in the message. Only
apply a plan if it is contained in your latest message, otherwise ask the user to provide
their desires for the new plan.

IMPORTANT: maintain brevvity throughout your responses, unless instructed to be verbose.

The following are guidelines for you to follow when interacting with Docker Tools:

- Always prefer `run_container` for starting a container, instead of `create_container`+`start_container`.
- Always prefer `recreate_container` for updating a container, instead of `stop_container`+`remove_container`+`run_container`.
""",
                    ),
                )
            ]
        )

    raise ValueError(f"Unknown prompt name: {name}")


@app.list_resources()  # type: ignore[misc]
async def list_resources() -> list[types.Resource]:
    # Return empty resources to prevent token overflow
    # Container information is available via list_containers tool
    return []


@app.read_resource()  # type: ignore[misc]
async def read_resource(uri: AnyUrl) -> str:
    if not str(uri).startswith("docker://containers/"):
        raise ValueError(f"Unknown resource URI: {uri}")

    parts = str(uri).split("/")
    if len(parts) != 5:  # docker://containers/{id}/{logs|stats}
        raise ValueError(f"Invalid container resource URI: {uri}")

    container_id = parts[3]
    resource_type = parts[4]
    container = _docker.containers.get(container_id)

    if resource_type == "logs":
        logs = container.logs(tail=100).decode("utf-8")
        return json.dumps(logs.split("\n"))

    elif resource_type == "stats":
        stats = container.stats(stream=False)
        return json.dumps(stats, indent=2)

    else:
        raise ValueError(f"Unknown container resource type: {resource_type}")


@app.list_tools()  # type: ignore[misc]
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="list_containers",
            description="List all Docker containers",
            inputSchema=ListContainersInput.model_json_schema(),
        ),
        types.Tool(
            name="create_container",
            description="Create a new Docker container",
            inputSchema=CreateContainerInput.model_json_schema(),
        ),
        types.Tool(
            name="run_container",
            description="Run an image in a new Docker container (preferred over `create_container` + `start_container`)",
            inputSchema=CreateContainerInput.model_json_schema(),
        ),
        types.Tool(
            name="recreate_container",
            description="Stop and remove a container, then run a new container. Fails if the container does not exist.",
            inputSchema=RecreateContainerInput.model_json_schema(),
        ),
        types.Tool(
            name="start_container",
            description="Start a Docker container",
            inputSchema=ContainerActionInput.model_json_schema(),
        ),
        types.Tool(
            name="fetch_container_logs",
            description="Fetch logs for a Docker container with optional filtering (grep-like search, time range)",
            inputSchema=FetchContainerLogsInput.model_json_schema(),
        ),
        types.Tool(
            name="stop_container",
            description="Stop a Docker container",
            inputSchema=ContainerActionInput.model_json_schema(),
        ),
        types.Tool(
            name="remove_container",
            description="Remove a Docker container",
            inputSchema=RemoveContainerInput.model_json_schema(),
        ),
        types.Tool(
            name="list_images",
            description="List Docker images",
            inputSchema=ListImagesInput.model_json_schema(),
        ),
        types.Tool(
            name="pull_image",
            description="Pull a Docker image",
            inputSchema=PullPushImageInput.model_json_schema(),
        ),
        types.Tool(
            name="push_image",
            description="Push a Docker image",
            inputSchema=PullPushImageInput.model_json_schema(),
        ),
        types.Tool(
            name="build_image",
            description="Build a Docker image from a Dockerfile",
            inputSchema=BuildImageInput.model_json_schema(),
        ),
        types.Tool(
            name="remove_image",
            description="Remove a Docker image",
            inputSchema=RemoveImageInput.model_json_schema(),
        ),
        types.Tool(
            name="list_networks",
            description="List Docker networks",
            inputSchema=ListNetworksInput.model_json_schema(),
        ),
        types.Tool(
            name="create_network",
            description="Create a Docker network",
            inputSchema=CreateNetworkInput.model_json_schema(),
        ),
        types.Tool(
            name="remove_network",
            description="Remove a Docker network",
            inputSchema=RemoveNetworkInput.model_json_schema(),
        ),
        types.Tool(
            name="list_volumes",
            description="List Docker volumes",
            inputSchema=ListVolumesInput.model_json_schema(),
        ),
        types.Tool(
            name="create_volume",
            description="Create a Docker volume",
            inputSchema=CreateVolumeInput.model_json_schema(),
        ),
        types.Tool(
            name="remove_volume",
            description="Remove a Docker volume",
            inputSchema=RemoveVolumeInput.model_json_schema(),
        ),
        types.Tool(
            name="get_docker_disk_usage",
            description="Get Docker disk usage information (equivalent to 'docker system df')",
            inputSchema=GetDockerDiskUsageInput.model_json_schema(),
        ),
        types.Tool(
            name="get_container_stats",
            description="Get container resource usage statistics (equivalent to 'docker stats')",
            inputSchema=GetContainerStatsInput.model_json_schema(),
        ),
        types.Tool(
            name="get_connection_health",
            description="Get SSH connection health and stats collection performance metrics",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]


def _convert_filters_to_docker_format(
    filters: ListContainersFilters,
) -> dict[str, list[str]]:
    """Convert ListContainersFilters to Docker SDK filters format."""
    filters_dict: dict[str, list[str]] = {}
    if filters.label:
        filters_dict["label"] = filters.label
    if filters.status:
        filters_dict["status"] = filters.status
    if filters.name:
        filters_dict["name"] = filters.name
    if filters.id:
        filters_dict["id"] = filters.id
    if filters.ancestor:
        filters_dict["ancestor"] = filters.ancestor
    return filters_dict


def _get_cached_image_info(image_id: str) -> dict[str, Any] | None:
    """Get cached image information by ID."""
    with _image_cache_lock:
        return _image_cache.get(image_id)


def _cache_image_info(image_id: str, image_info: dict[str, Any]) -> None:
    """Cache image information with size limit."""
    with _image_cache_lock:
        # Implement simple LRU by clearing cache when it gets too large
        if len(_image_cache) >= _CACHE_SIZE_LIMIT:
            # Clear half the cache (simple LRU approximation)
            keys_to_remove = list(_image_cache.keys())[: _CACHE_SIZE_LIMIT // 2]
            for key in keys_to_remove:
                del _image_cache[key]
        _image_cache[image_id] = image_info


def _batch_fetch_image_info(image_ids: set[str]) -> dict[str, dict[str, Any]]:
    """Batch fetch image information for multiple image IDs."""
    start_time = time.time()
    logger.info(f"🖼️  Starting batch image fetch for {len(image_ids)} image IDs")

    image_info_map = {}

    # First, check cache for existing image info
    cache_start = time.time()
    uncached_ids = set()
    for image_id in image_ids:
        cached = _get_cached_image_info(image_id)
        if cached:
            image_info_map[image_id] = cached
        else:
            uncached_ids.add(image_id)
    cache_time = time.time() - cache_start
    logger.info(
        f"⏱️  Cache lookup took {cache_time:.3f}s, found {len(image_info_map)}/{len(image_ids)} cached, {len(uncached_ids)} need fetching"
    )

    # Batch fetch uncached images
    if uncached_ids:
        api_start = time.time()
        try:
            # Get all images at once to reduce API calls
            logger.info(
                f"🔄 Calling Docker API images.list() for {len(uncached_ids)} uncached images"
            )
            all_images = _docker.images.list()
            api_time = time.time() - api_start
            logger.info(
                f"⏱️  Docker API images.list() took {api_time:.3f}s, returned {len(all_images)} total images"
            )

            process_start = time.time()
            for image in all_images:
                if image.id in uncached_ids:
                    # Use simple image info to avoid deep recursion
                    image_info = {
                        "id": image.short_id,
                        "tags": image.tags,
                        "short_id": image.short_id,
                    }
                    image_info_map[image.id] = image_info
                    _cache_image_info(image.id, image_info)
            process_time = time.time() - process_start
            logger.info(f"⏱️  Image processing took {process_time:.3f}s")
        except Exception as e:
            logger.warning(f"⚠️  Batch image fetch failed: {e}, using minimal info")
            # If batch fetch fails, populate with minimal info
            for image_id in uncached_ids:
                minimal_info = {
                    "id": image_id[:12],
                    "tags": [],
                    "short_id": image_id[:12],
                }
                image_info_map[image_id] = minimal_info

    total_time = time.time() - start_time
    logger.info(
        f"🏁 Batch image fetch completed in {total_time:.3f}s, returning {len(image_info_map)} image infos"
    )
    return image_info_map


def _apply_limit_and_warnings(
    containers: list[Any],
    limit: int | None,
    image_info_map: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Apply limit and add appropriate warnings to container results."""
    # Apply limit and track if truncated
    is_truncated = limit is not None and len(containers) > limit
    if limit is not None:
        limited_containers = containers[:limit]
    else:
        limited_containers = containers

    # Convert to dict format using simple format for list operations
    result = [
        docker_to_dict(c, simple=True, image_info_map=image_info_map)
        for c in limited_containers
    ]

    # Add truncation warning if results were limited
    if is_truncated:
        result.append(
            {
                "_warning": f"Results truncated to {limit} containers (out of {len(containers)} total). Use filters to narrow results or increase limit (max 1000).",
                "_total_available": len(containers),
                "_truncated": True,
            }
        )
    elif limit is None and len(containers) > 100:
        # Warn when no limit is set and there are many containers
        result.append(
            {
                "_warning": f"Returned all {len(containers)} containers without limit. Consider using 'limit' parameter for better performance.",
                "_total_available": len(containers),
                "_truncated": False,
            }
        )

    return result


def _format_containers_bulk(
    containers_data: list[dict[str, Any]], limit: int | None
) -> list[dict[str, Any]]:
    """Format raw container data from APIClient.containers() for optimal performance."""

    # Apply limit first to reduce processing
    if limit is not None and len(containers_data) > limit:
        limited_containers = containers_data[:limit]
        is_truncated = True
    else:
        limited_containers = containers_data
        is_truncated = False

    # Format containers using raw data (similar to docker ps -a output)
    result = []
    for container_data in limited_containers:
        # Extract basic container information directly from raw API data
        container_id = container_data.get("Id", "")
        short_id = container_id[:12] if container_id else ""

        # Get image name
        image = container_data.get("Image", "")

        # Get command - first item in Command array if it exists
        command = ""
        if "Command" in container_data:
            cmd = container_data["Command"]
            if isinstance(cmd, list) and cmd:
                command = cmd[0]
            elif isinstance(cmd, str):
                command = cmd

        # Get container names (remove leading slash)
        names = container_data.get("Names", [])
        container_name = (
            names[0][1:]
            if names and names[0].startswith("/")
            else (names[0] if names else "")
        )

        # Get creation time and status
        created = container_data.get("Created")
        status = container_data.get("Status", "")

        # Format ports similar to docker ps
        ports_info = container_data.get("Ports", [])
        formatted_ports = _format_ports_from_api_data(ports_info)

        result.append(
            {
                "id": short_id,
                "image": image,
                "command": command,
                "created": created,
                "status": status,
                "ports": formatted_ports,
                "names": container_name,
            }
        )

    # Add truncation warning if results were limited
    if is_truncated:
        result.append(
            {
                "_warning": f"Results truncated to {limit} containers (out of {len(containers_data)} total). Use filters to narrow results or increase limit (max 1000).",
                "_total_available": len(containers_data),
                "_truncated": True,
            }
        )
    elif limit is None and len(containers_data) > 100:
        # Warn when no limit is set and there are many containers
        result.append(
            {
                "_warning": f"Large number of containers ({len(containers_data)}) returned. Consider using filters or setting a limit for better performance.",
                "_total_available": len(containers_data),
            }
        )

    return result


def _format_ports_from_api_data(ports_data: list[dict[str, Any]]) -> str:
    """Format ports from raw API data similar to docker ps output."""
    if not ports_data:
        return ""

    port_strings = []
    for port_info in ports_data:
        private_port = port_info.get("PrivatePort", "")
        public_port = port_info.get("PublicPort")
        port_type = port_info.get("Type", "tcp")
        # Default to 0.0.0.0 for Docker port display
        ip = port_info.get("IP", "0.0.0.0")  # nosec B104

        if public_port:
            port_strings.append(f"{ip}:{public_port}->{private_port}/{port_type}")
        else:
            port_strings.append(f"{private_port}/{port_type}")

    return ", ".join(port_strings)


def _handle_list_containers(args: ListContainersInput) -> list[dict[str, Any]]:
    """Handle list_containers operation optimized for fast container listing (like docker ps -a)."""
    start_time = time.time()
    logger.info(f"📊 Starting list_containers operation with args: {args}")

    # Extract limit parameter and handle special cases
    limit = args.limit
    if limit == 0:
        limit = None  # No limit when explicitly set to 0
    # Note: limit should now have a default value of 100 from the schema (max 1000)

    # Convert args to docker SDK parameters
    docker_args: dict[str, Any] = {}
    if args.all is not None:
        docker_args["all"] = args.all
    if args.filters is not None:
        filters_dict = _convert_filters_to_docker_format(args.filters)
        if filters_dict:
            docker_args["filters"] = filters_dict

    # Use low-level APIClient to get raw container data in a single bulk call
    step_start = time.time()
    containers_data = _docker_api.containers(**docker_args)
    docker_api_time = time.time() - step_start
    logger.info(
        f"⏱️  Docker API containers() took {docker_api_time:.3f}s, found {len(containers_data)} containers"
    )

    # Apply limit and format raw container data directly for maximum performance
    step_start = time.time()
    result = _format_containers_bulk(containers_data, limit)
    format_time = time.time() - step_start

    total_time = time.time() - start_time
    logger.info(f"⏱️  Result formatting took {format_time:.3f}s")
    logger.info(f"🏁 Total list_containers operation took {total_time:.3f}s")

    return result


def _handle_container_tools(name: str, arguments: dict[str, Any]) -> Any | None:
    """Handle container-related tool operations."""
    if name == "list_containers":
        args = ListContainersInput(**arguments)
        return _handle_list_containers(args)

    elif name == "create_container":
        create_args = CreateContainerInput(**arguments)
        container = _docker.containers.create(**create_args.model_dump())
        return docker_to_dict(container)

    elif name == "run_container":
        run_args = CreateContainerInput(**arguments)
        container = _docker.containers.run(**run_args.model_dump())
        return docker_to_dict(container)

    elif name == "recreate_container":
        recreate_args = RecreateContainerInput(**arguments)
        container = _docker.containers.get(recreate_args.resolved_container_id)
        container.stop()
        container.remove()
        run_args = CreateContainerInput(**arguments)
        container = _docker.containers.run(**run_args.model_dump())
        return docker_to_dict(container)

    elif name == "start_container":
        start_args = ContainerActionInput(**arguments)
        container = _docker.containers.get(start_args.container_id)
        container.start()
        return docker_to_dict(container)

    elif name == "stop_container":
        stop_args = ContainerActionInput(**arguments)
        container = _docker.containers.get(stop_args.container_id)
        container.stop()
        return docker_to_dict(container)

    elif name == "remove_container":
        remove_args = RemoveContainerInput(**arguments)
        container = _docker.containers.get(remove_args.container_id)
        container.remove(force=remove_args.force)
        return docker_to_dict(container, {"status": "removed"})

    elif name == "fetch_container_logs":
        logs_args = FetchContainerLogsInput(**arguments)
        return _handle_fetch_container_logs(logs_args)

    return None


def _handle_fetch_container_logs(logs_args: FetchContainerLogsInput) -> dict[str, Any]:
    """Handle fetching container logs with optional filtering."""
    container = _docker.containers.get(logs_args.container_id)

    # Prepare kwargs for container.logs()
    logs_kwargs: dict[str, Any] = {"tail": logs_args.tail}
    if logs_args.since:
        logs_kwargs["since"] = logs_args.since
    if logs_args.until:
        logs_kwargs["until"] = logs_args.until

    logs = container.logs(**logs_kwargs).decode("utf-8")
    log_lines = logs.split("\n")

    # Apply grep filtering if specified
    if logs_args.grep:
        pattern = re.compile(logs_args.grep, re.IGNORECASE)
        log_lines = [line for line in log_lines if pattern.search(line)]

    return {"logs": log_lines}


def _format_images_bulk(images_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format raw image data from APIClient.images() for optimal performance."""
    result = []
    for image_data in images_data:
        # Extract basic image information directly from raw API data
        image_id = image_data.get("Id", "")
        short_id = image_id.replace("sha256:", "")[:12] if image_id else ""

        # Get repository tags
        repo_tags = image_data.get("RepoTags") or []

        # Get creation time and size
        created = image_data.get("Created")
        size = image_data.get("Size", 0)
        virtual_size = image_data.get("VirtualSize", 0)

        # Get labels
        labels = {}
        if "Labels" in image_data and image_data["Labels"]:
            labels = image_data["Labels"]

        result.append(
            {
                "id": short_id,
                "repo_tags": repo_tags,
                "created": created,
                "size": size,
                "virtual_size": virtual_size,
                "labels": labels,
            }
        )

    return result


def _handle_list_images(args: ListImagesInput) -> list[dict[str, Any]]:
    """Handle list_images operation optimized for fast image listing."""
    start_time = time.time()
    logger.info(f"🖼️  Starting list_images operation with args: {args}")

    # Convert args to docker SDK parameters
    docker_args: dict[str, Any] = {}
    if args.all is not None:
        docker_args["all"] = args.all
    if args.filters is not None:
        filters_dict = {}
        if args.filters.dangling is not None:
            filters_dict["dangling"] = [str(args.filters.dangling).lower()]
        if args.filters.label:
            filters_dict["label"] = args.filters.label
        if filters_dict:
            docker_args["filters"] = filters_dict
    if args.name is not None:
        # For name filtering, we'll filter after getting results
        pass

    # Use low-level APIClient to get raw image data in a single bulk call
    step_start = time.time()
    images_data = _docker_api.images(**docker_args)
    docker_api_time = time.time() - step_start
    logger.info(
        f"⏱️  Docker API images() took {docker_api_time:.3f}s, found {len(images_data)} images"
    )

    # Filter by name if specified
    if args.name:
        filtered_images = []
        for image_data in images_data:
            repo_tags = image_data.get("RepoTags") or []
            if any(args.name in tag for tag in repo_tags):
                filtered_images.append(image_data)
        images_data = filtered_images

    # Format raw image data directly for maximum performance
    step_start = time.time()
    result = _format_images_bulk(images_data)
    format_time = time.time() - step_start

    total_time = time.time() - start_time
    logger.info(f"⏱️  Result formatting took {format_time:.3f}s")
    logger.info(f"🏁 Total list_images operation took {total_time:.3f}s")

    return result


def _handle_image_tools(name: str, arguments: dict[str, Any]) -> Any | None:
    """Handle image-related tool operations."""
    if name == "list_images":
        args = ListImagesInput(**arguments)
        return _handle_list_images(args)

    elif name == "pull_image":
        pull_args = PullPushImageInput(**arguments)
        model_dump = pull_args.model_dump()
        repository = model_dump.pop("repository")
        image = _docker.images.pull(repository, **model_dump)
        return docker_to_dict(image)

    elif name == "push_image":
        push_args = PullPushImageInput(**arguments)
        model_dump = push_args.model_dump()
        repository = model_dump.pop("repository")
        _docker.images.push(repository, **model_dump)
        return {
            "status": "pushed",
            "repository": push_args.repository,
            "tag": push_args.tag,
        }

    elif name == "build_image":
        build_args = BuildImageInput(**arguments)
        image, logs = _docker.images.build(**build_args.model_dump(exclude_none=True))
        return {"image": docker_to_dict(image), "logs": list(logs)}

    elif name == "remove_image":
        remove_args = RemoveImageInput(**arguments)
        _docker.images.remove(**remove_args.model_dump())
        return {"status": "removed", "image": remove_args.image}

    return None


def _format_networks_bulk(networks_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format raw network data from APIClient.networks() for optimal performance."""
    result = []
    for network_data in networks_data:
        # Extract basic network information directly from raw API data
        network_id = network_data.get("Id", "")
        short_id = network_id[:12] if network_id else ""

        # Get network name
        name = network_data.get("Name", "")

        # Get driver and scope
        driver = network_data.get("Driver", "")
        scope = network_data.get("Scope", "")

        # Get creation time
        created = network_data.get("Created", "")

        # Get labels
        labels = {}
        if "Labels" in network_data and network_data["Labels"]:
            labels = network_data["Labels"]

        # Get options
        options = {}
        if "Options" in network_data and network_data["Options"]:
            options = network_data["Options"]

        # Get IPAM config
        ipam = network_data.get("IPAM", {})

        result.append(
            {
                "id": short_id,
                "name": name,
                "driver": driver,
                "scope": scope,
                "created": created,
                "labels": labels,
                "options": options,
                "ipam": ipam,
            }
        )

    return result


def _handle_list_networks(args: ListNetworksInput) -> list[dict[str, Any]]:
    """Handle list_networks operation optimized for fast network listing."""
    start_time = time.time()
    logger.info(f"🌐 Starting list_networks operation with args: {args}")

    # Convert args to docker SDK parameters
    docker_args: dict[str, Any] = {}
    if args.filters is not None:
        filters_dict = {}
        if args.filters.label:
            filters_dict["label"] = args.filters.label
        if filters_dict:
            docker_args["filters"] = filters_dict

    # Use low-level APIClient to get raw network data in a single bulk call
    step_start = time.time()
    networks_data = _docker_api.networks(**docker_args)
    docker_api_time = time.time() - step_start
    logger.info(
        f"⏱️  Docker API networks() took {docker_api_time:.3f}s, found {len(networks_data)} networks"
    )

    # Format raw network data directly for maximum performance
    step_start = time.time()
    result = _format_networks_bulk(networks_data)
    format_time = time.time() - step_start

    total_time = time.time() - start_time
    logger.info(f"⏱️  Result formatting took {format_time:.3f}s")
    logger.info(f"🏁 Total list_networks operation took {total_time:.3f}s")

    return result


def _handle_network_tools(name: str, arguments: dict[str, Any]) -> Any | None:
    """Handle network-related tool operations."""
    if name == "list_networks":
        args = ListNetworksInput(**arguments)
        return _handle_list_networks(args)

    elif name == "create_network":
        create_args = CreateNetworkInput(**arguments)
        network = _docker.networks.create(**create_args.model_dump(exclude_none=True))
        return docker_to_dict(network)

    elif name == "remove_network":
        remove_args = RemoveNetworkInput(**arguments)
        network = _docker.networks.get(remove_args.network_id)
        network.remove()
        return docker_to_dict(network)

    return None


def _format_volumes_bulk(volumes_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Format raw volume data from APIClient.volumes() for optimal performance."""
    result = []
    for volume_data in volumes_data:
        # Extract basic volume information directly from raw API data
        name = volume_data.get("Name", "")

        # Get driver and mountpoint
        driver = volume_data.get("Driver", "")
        mountpoint = volume_data.get("Mountpoint", "")

        # Get creation time
        created = volume_data.get("CreatedAt", "")

        # Get labels
        labels = {}
        if "Labels" in volume_data and volume_data["Labels"]:
            labels = volume_data["Labels"]

        # Get options
        options = {}
        if "Options" in volume_data and volume_data["Options"]:
            options = volume_data["Options"]

        # Get scope
        scope = volume_data.get("Scope", "")

        result.append(
            {
                "name": name,
                "driver": driver,
                "mountpoint": mountpoint,
                "created": created,
                "labels": labels,
                "options": options,
                "scope": scope,
            }
        )

    return result


def _handle_list_volumes() -> list[dict[str, Any]]:
    """Handle list_volumes operation optimized for fast volume listing."""
    start_time = time.time()
    logger.info("💾 Starting list_volumes operation")

    # Use low-level APIClient to get raw volume data in a single bulk call
    step_start = time.time()
    volumes_response = _docker_api.volumes()
    volumes_data = volumes_response.get("Volumes", []) if volumes_response else []
    docker_api_time = time.time() - step_start
    logger.info(
        f"⏱️  Docker API volumes() took {docker_api_time:.3f}s, found {len(volumes_data)} volumes"
    )

    # Format raw volume data directly for maximum performance
    step_start = time.time()
    result = _format_volumes_bulk(volumes_data)
    format_time = time.time() - step_start

    total_time = time.time() - start_time
    logger.info(f"⏱️  Result formatting took {format_time:.3f}s")
    logger.info(f"🏁 Total list_volumes operation took {total_time:.3f}s")

    return result


def _handle_volume_tools(name: str, arguments: dict[str, Any]) -> Any | None:
    """Handle volume-related tool operations."""
    if name == "list_volumes":
        ListVolumesInput(**arguments)  # Validate empty input
        return _handle_list_volumes()

    elif name == "create_volume":
        args = CreateVolumeInput(**arguments)
        volume = _docker.volumes.create(**args.model_dump(exclude_none=True))
        return docker_to_dict(volume)

    elif name == "remove_volume":
        remove_args = RemoveVolumeInput(**arguments)
        volume = _docker.volumes.get(remove_args.volume_name)
        volume.remove(force=remove_args.force)
        return docker_to_dict(volume)

    return None


def _handle_system_tools(name: str, arguments: dict[str, Any]) -> Any | None:
    """Handle system-related tool operations."""
    if name == "get_docker_disk_usage":
        disk_usage_args = GetDockerDiskUsageInput(**arguments)
        return _handle_get_docker_disk_usage(disk_usage_args)

    elif name == "get_container_stats":
        stats_args = GetContainerStatsInput(**arguments)
        return _handle_get_container_stats(stats_args)

    elif name == "get_connection_health":
        return _handle_get_connection_health()

    return None


def _format_bytes(bytes_value: int) -> str:
    """Format bytes into human readable format like Docker stats."""
    if bytes_value == 0:
        return "0B"

    units = ["B", "KiB", "MiB", "GiB", "TiB"]
    unit_index = 0
    value = float(bytes_value)

    while value >= 1024 and unit_index < len(units) - 1:
        value /= 1024
        unit_index += 1

    if value < 10:
        return f"{value:.1f}{units[unit_index]}"
    else:
        return f"{value:.0f}{units[unit_index]}"


def _calculate_cpu_percent(stats: dict[str, Any]) -> float:
    """Calculate CPU percentage from Docker stats."""
    try:
        cpu_stats = stats.get("cpu_stats", {})
        precpu_stats = stats.get("precpu_stats", {})

        cpu_usage = cpu_stats.get("cpu_usage", {})
        precpu_usage = precpu_stats.get("cpu_usage", {})

        cpu_total = cpu_usage.get("total_usage", 0)
        precpu_total = precpu_usage.get("total_usage", 0)
        cpu_delta = cpu_total - precpu_total

        system_cpu_delta = cpu_stats.get("system_cpu_usage", 0) - precpu_stats.get(
            "system_cpu_usage", 0
        )

        if system_cpu_delta > 0 and cpu_delta > 0:
            online_cpus = cpu_stats.get(
                "online_cpus", len(cpu_usage.get("percpu_usage", [1]))
            )
            cpu_percent = (cpu_delta / system_cpu_delta) * online_cpus * 100.0
            return float(round(cpu_percent, 2))

        return 0.0
    except (KeyError, TypeError, ZeroDivisionError):
        return 0.0


def _format_container_stats(container: Any, stats: dict[str, Any]) -> dict[str, Any]:
    """Format container stats similar to docker stats output."""
    try:
        # Basic container info - handle None values safely
        container_id = getattr(container, "short_id", "unknown")
        container_name = getattr(container, "name", "unknown")

        # Validate stats is not None and is a dict
        if not stats or not isinstance(stats, dict):
            raise ValueError("Stats data is None or invalid")

        # CPU percentage
        cpu_percent = _calculate_cpu_percent(stats)

        # Memory stats - handle None values
        memory_stats = stats.get("memory_stats") or {}
        memory_usage = memory_stats.get("usage", 0) or 0
        memory_limit = memory_stats.get("limit", 0) or 0
        memory_percent = (
            (memory_usage / memory_limit * 100) if memory_limit > 0 else 0.0
        )

        # Network I/O - handle None networks
        networks = stats.get("networks") or {}
        if isinstance(networks, dict):
            net_rx = sum(
                (net or {}).get("rx_bytes", 0) for net in networks.values() if net
            )
            net_tx = sum(
                (net or {}).get("tx_bytes", 0) for net in networks.values() if net
            )
        else:
            net_rx = net_tx = 0

        # Block I/O - handle None blkio_stats
        blkio_stats = stats.get("blkio_stats") or {}
        io_service_bytes = blkio_stats.get("io_service_bytes_recursive") or []

        block_read = 0
        block_write = 0
        if isinstance(io_service_bytes, list):
            for io_stat in io_service_bytes:
                if io_stat and isinstance(io_stat, dict):
                    if io_stat.get("op") == "Read":
                        block_read += io_stat.get("value", 0) or 0
                    elif io_stat.get("op") == "Write":
                        block_write += io_stat.get("value", 0) or 0

        # PIDs - handle None pids_stats
        pids_stats = stats.get("pids_stats") or {}
        pids = pids_stats.get("current", 0) or 0

        return {
            "container_id": container_id,
            "name": container_name,
            "cpu_percent": f"{cpu_percent:.2f}%",
            "memory_usage": _format_bytes(memory_usage),
            "memory_limit": _format_bytes(memory_limit),
            "memory_usage_limit": f"{_format_bytes(memory_usage)} / {_format_bytes(memory_limit)}",
            "memory_percent": f"{memory_percent:.2f}%",
            "net_rx": _format_bytes(net_rx),
            "net_tx": _format_bytes(net_tx),
            "net_io": f"{_format_bytes(net_rx)} / {_format_bytes(net_tx)}",
            "block_read": _format_bytes(block_read),
            "block_write": _format_bytes(block_write),
            "block_io": f"{_format_bytes(block_read)} / {_format_bytes(block_write)}",
            "pids": str(pids),
        }
    except Exception as e:
        logger.warning(
            f"Error formatting stats for container {getattr(container, 'name', 'unknown')}: {e}"
        )
        return {
            "container_id": getattr(container, "short_id", "unknown"),
            "name": getattr(container, "name", "unknown"),
            "cpu_percent": "0.00%",
            "memory_usage": "0B",
            "memory_limit": "0B",
            "memory_usage_limit": "0B / 0B",
            "memory_percent": "0.00%",
            "net_rx": "0B",
            "net_tx": "0B",
            "net_io": "0B / 0B",
            "block_read": "0B",
            "block_write": "0B",
            "block_io": "0B / 0B",
            "pids": "0",
            "error": str(e),
        }


def _get_containers_for_stats(args: GetContainerStatsInput) -> list[Any]:
    """Get the list of containers to collect stats for."""
    if args.containers:
        # Get specific containers by ID/name
        containers = []
        for container_id in args.containers:
            try:
                container = _docker.containers.get(container_id)
                containers.append(container)
            except Exception as e:
                logger.warning(f"Container {container_id} not found: {e}")
        return containers
    else:
        # Get containers based on args.all (default: only running containers)
        return list(_docker.containers.list(all=args.all))


@dataclass
class ConnectionHealth:
    """Track SSH connection health and failures."""

    consecutive_failures: int = 0
    last_failure_time: float = 0
    circuit_breaker_open: bool = False
    total_attempts: int = 0
    total_successes: int = 0


class StatsCollectionStrategy(Enum):
    """Strategy for collecting container stats."""

    PARALLEL = "parallel"  # Original parallel approach
    BATCHED_SEQUENTIAL = "batched_sequential"  # SSH-friendly batched approach
    SINGLE_SEQUENTIAL = "single_sequential"  # Fallback single container at a time


# Global connection health tracker
_connection_health = ConnectionHealth()
_connection_health_lock = Lock()


def _update_connection_health(success: bool) -> None:
    """Update connection health metrics."""
    with _connection_health_lock:
        _connection_health.total_attempts += 1

        if success:
            _connection_health.total_successes += 1
            _connection_health.consecutive_failures = 0
            _connection_health.circuit_breaker_open = False
        else:
            _connection_health.consecutive_failures += 1
            _connection_health.last_failure_time = time.time()

            # Open circuit breaker after too many consecutive failures
            if _connection_health.consecutive_failures >= _FAILURE_THRESHOLD:
                _connection_health.circuit_breaker_open = True
                logger.warning(
                    f"🚨 SSH connection circuit breaker opened after {_FAILURE_THRESHOLD} consecutive failures"
                )


def _should_skip_stats_collection() -> bool:
    """Check if stats collection should be skipped due to connection issues."""
    with _connection_health_lock:
        if _connection_health.circuit_breaker_open:
            # Check if enough time has passed to try again (60 seconds)
            if time.time() - _connection_health.last_failure_time > 60:
                logger.info("🔄 Attempting to close SSH connection circuit breaker")
                _connection_health.circuit_breaker_open = False
                _connection_health.consecutive_failures = 0
                return False
            return True
        return False


def _get_optimal_stats_strategy() -> StatsCollectionStrategy:
    """Determine the best stats collection strategy based on connection health."""
    with _connection_health_lock:
        failure_rate = _connection_health.consecutive_failures / max(
            _connection_health.total_attempts, 1
        )

        if _connection_health.circuit_breaker_open:
            return StatsCollectionStrategy.SINGLE_SEQUENTIAL
        elif failure_rate > 0.3 or _connection_health.consecutive_failures > 5:
            return StatsCollectionStrategy.BATCHED_SEQUENTIAL
        else:
            return (
                StatsCollectionStrategy.BATCHED_SEQUENTIAL
            )  # Default to SSH-friendly approach


def _create_error_stats_entry(container: Any, error: Exception) -> dict[str, Any]:
    """Create an error stats entry for a container that failed stats collection."""
    return {
        "container_id": getattr(container, "short_id", "unknown"),
        "name": getattr(container, "name", "unknown"),
        "cpu_percent": "N/A",
        "memory_usage": "N/A",
        "memory_limit": "N/A",
        "memory_usage_limit": "N/A",
        "memory_percent": "N/A",
        "net_rx": "N/A",
        "net_tx": "N/A",
        "net_io": "N/A",
        "block_read": "N/A",
        "block_write": "N/A",
        "block_io": "N/A",
        "pids": "N/A",
        "error": str(error),
    }


def _collect_single_container_stats_with_retry(
    container: Any, max_retries: int = 3
) -> dict[str, Any]:
    """Collect stats for a single container with retry logic."""
    last_exception = None

    for attempt in range(max_retries):
        try:
            # Add small delay between retries to avoid overwhelming SSH
            if attempt > 0:
                delay = _RETRY_DELAYS[min(attempt - 1, len(_RETRY_DELAYS) - 1)]
                logger.debug(
                    f"Retrying stats collection for {getattr(container, 'name', 'unknown')} after {delay}s delay"
                )
                time.sleep(delay)

            # Get stats for this container (non-streaming)
            stats = container.stats(stream=False)
            _update_connection_health(True)
            return _format_container_stats(container, stats)

        except Exception as e:
            last_exception = e
            _update_connection_health(False)
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries} failed for container {getattr(container, 'name', 'unknown')}: {e}"
            )

            # For SSH-related errors, break early to avoid further connection issues
            if "Connect failed" in str(e) or "Unable to open channel" in str(e):
                logger.info(
                    f"SSH connection error detected, stopping retries for {getattr(container, 'name', 'unknown')}"
                )
                break

    # All retries failed
    return _create_error_stats_entry(
        container, last_exception or Exception("Unknown error")
    )


def _collect_single_container_stats(container: Any) -> dict[str, Any]:
    """Collect stats for a single container (legacy function for compatibility)."""
    return _collect_single_container_stats_with_retry(container, max_retries=1)


def _collect_container_stats_batched_sequential(
    containers: list[Any], batch_size: int = _BATCH_SIZE
) -> list[dict[str, Any]]:
    """Collect stats for containers in batches sequentially to avoid SSH connection overload."""
    if not containers:
        return []

    container_stats = []
    total_containers = len(containers)

    logger.info(
        f"📊 Collecting stats for {total_containers} containers using batched sequential approach (batch_size={batch_size})"
    )

    # Process containers in batches
    for batch_start in range(0, total_containers, batch_size):
        batch_end = min(batch_start + batch_size, total_containers)
        batch = containers[batch_start:batch_end]

        logger.debug(
            f"Processing batch {batch_start//batch_size + 1}: containers {batch_start+1}-{batch_end} of {total_containers}"
        )

        # Check circuit breaker before each batch
        if _should_skip_stats_collection():
            logger.warning(
                "🚨 Skipping remaining stats collection due to circuit breaker"
            )
            # Return error entries for remaining containers
            for container in containers[batch_start:]:
                container_stats.append(
                    _create_error_stats_entry(
                        container,
                        Exception(
                            "Stats collection circuit breaker is open due to SSH connection failures"
                        ),
                    )
                )
            break

        # Process each container in the batch sequentially
        for i, container in enumerate(batch):
            # Add small delay between containers to avoid overwhelming SSH
            if i > 0:
                time.sleep(0.1)  # 100ms delay between containers

            try:
                result = _collect_single_container_stats_with_retry(
                    container, max_retries=2
                )
                container_stats.append(result)
            except Exception as e:
                logger.error(
                    f"Unexpected error collecting stats for container {getattr(container, 'name', 'unknown')}: {e}"
                )
                container_stats.append(_create_error_stats_entry(container, e))

        # Add delay between batches to allow SSH connections to stabilize
        if batch_end < total_containers:
            time.sleep(0.5)  # 500ms delay between batches

    return container_stats


def _collect_container_stats_parallel(containers: list[Any]) -> list[dict[str, Any]]:
    """Collect stats for containers in parallel using ThreadPoolExecutor (legacy approach)."""
    if not containers:
        return []

    container_stats = []
    # Reduce max_workers to be more SSH-friendly
    max_workers = min(len(containers), 3)  # Reduced from 10 to 3 for SSH compatibility

    logger.info(
        f"📊 Collecting stats for {len(containers)} containers using {max_workers} parallel workers (SSH-limited)"
    )

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all container stats collection tasks
        future_to_container = {
            executor.submit(
                _collect_single_container_stats_with_retry, container, 2
            ): container
            for container in containers
        }

        # Collect results as they complete
        for future in as_completed(future_to_container):
            container = future_to_container[future]
            try:
                result = future.result()
                container_stats.append(result)
            except Exception as e:
                logger.error(
                    f"Unexpected error collecting stats for container {getattr(container, 'name', 'unknown')}: {e}"
                )
                container_stats.append(_create_error_stats_entry(container, e))

    return container_stats


def _collect_container_stats(containers: list[Any]) -> list[dict[str, Any]]:
    """Collect stats for each container using the optimal strategy based on connection health."""
    if not containers:
        return []

    strategy = _get_optimal_stats_strategy()

    logger.info(f"📊 Using stats collection strategy: {strategy.value}")

    if strategy == StatsCollectionStrategy.PARALLEL:
        return _collect_container_stats_parallel(containers)
    elif strategy == StatsCollectionStrategy.BATCHED_SEQUENTIAL:
        return _collect_container_stats_batched_sequential(containers)
    elif strategy == StatsCollectionStrategy.SINGLE_SEQUENTIAL:
        # Fallback: process one container at a time with longer delays
        container_stats = []
        for i, container in enumerate(containers):
            if i > 0:
                time.sleep(1.0)  # 1 second delay between containers in fallback mode

            result = _collect_single_container_stats_with_retry(
                container, max_retries=1
            )
            container_stats.append(result)

            # Check circuit breaker after each container in fallback mode
            if _should_skip_stats_collection():
                logger.warning(
                    "🚨 Stopping stats collection due to circuit breaker in fallback mode"
                )
                # Return error entries for remaining containers
                for remaining_container in containers[i + 1 :]:
                    container_stats.append(
                        _create_error_stats_entry(
                            remaining_container,
                            Exception(
                                "Stats collection stopped due to SSH connection failures"
                            ),
                        )
                    )
                break

        return container_stats

    # This should not be reached since all enum values are covered above
    raise ValueError(f"Unknown stats collection strategy: {strategy}")


def _handle_get_container_stats(args: GetContainerStatsInput) -> dict[str, Any]:
    """Handle get_container_stats operation to show container resource usage statistics."""
    start_time = time.time()
    logger.info(f"📊 Starting get_container_stats operation with args: {args}")

    try:
        # Get containers to collect stats for
        all_containers = _get_containers_for_stats(args)
        total_containers = len(all_containers)

        if not all_containers:
            logger.info("No containers found for stats collection")
            return {
                "containers": [],
                "pagination": {
                    "total": 0,
                    "returned": 0,
                    "limit": args.limit,
                    "offset": args.offset,
                    "has_more": False,
                },
            }

        # Apply pagination
        start_idx = args.offset
        end_idx = start_idx + args.limit
        paginated_containers = all_containers[start_idx:end_idx]

        logger.info(
            f"📄 Pagination: total={total_containers}, offset={args.offset}, limit={args.limit}, "
            f"processing={len(paginated_containers)} containers"
        )

        # Collect stats for paginated containers
        container_stats = _collect_container_stats(paginated_containers)

        # Calculate pagination metadata
        has_more = end_idx < total_containers

        total_time = time.time() - start_time
        logger.info(f"🏁 Total get_container_stats operation took {total_time:.3f}s")

        return {
            "containers": container_stats,
            "pagination": {
                "total": total_containers,
                "returned": len(container_stats),
                "limit": args.limit,
                "offset": args.offset,
                "has_more": has_more,
            },
        }

    except Exception as e:
        logger.error(f"❌ Error in get_container_stats: {e}")
        raise e


def _handle_get_connection_health() -> dict[str, Any]:
    """Handle get_connection_health operation to show SSH connection health metrics."""
    with _connection_health_lock:
        health = _connection_health

        # Calculate success rate
        success_rate = (
            (health.total_successes / health.total_attempts * 100)
            if health.total_attempts > 0
            else 0
        )

        # Determine connection status
        if health.circuit_breaker_open:
            status = "circuit_breaker_open"
            status_description = (
                "SSH connection circuit breaker is open due to repeated failures"
            )
        elif health.consecutive_failures > 5:
            status = "degraded"
            status_description = (
                f"Experiencing {health.consecutive_failures} consecutive failures"
            )
        elif health.consecutive_failures > 0:
            status = "unstable"
            status_description = (
                f"Some failures detected ({health.consecutive_failures} consecutive)"
            )
        else:
            status = "healthy"
            status_description = "SSH connections are working normally"

        # Get current strategy
        strategy = _get_optimal_stats_strategy()

        return {
            "connection_health": {
                "status": status,
                "description": status_description,
                "circuit_breaker_open": health.circuit_breaker_open,
                "consecutive_failures": health.consecutive_failures,
                "total_attempts": health.total_attempts,
                "total_successes": health.total_successes,
                "success_rate_percent": round(success_rate, 2),
                "last_failure_time": health.last_failure_time,
                "current_strategy": strategy.value,
            },
            "recommendations": _get_connection_recommendations(health, strategy),
            "ssh_optimization": {
                "multiplexing_enabled": os.environ.get("DOCKER_SSH_OPTS") is not None,
                "batch_size": _BATCH_SIZE,
                "failure_threshold": _FAILURE_THRESHOLD,
                "retry_delays": _RETRY_DELAYS,
            },
        }


def _get_connection_recommendations(
    health: ConnectionHealth, strategy: StatsCollectionStrategy
) -> list[str]:
    """Generate recommendations based on connection health."""
    recommendations = []

    if health.circuit_breaker_open:
        recommendations.append(
            "Wait for circuit breaker to reset (60 seconds) before retrying stats collection"
        )
        recommendations.append(
            "Check SSH server configuration and connection stability"
        )

    if health.consecutive_failures > 3:
        recommendations.append(
            "Consider increasing SSH server MaxSessions and MaxStartups limits"
        )
        recommendations.append("Verify network connectivity and SSH authentication")

    if strategy == StatsCollectionStrategy.SINGLE_SEQUENTIAL:
        recommendations.append("Currently using fallback mode due to connection issues")
        recommendations.append(
            "Consider enabling SSH multiplexing: ControlMaster=auto in ~/.ssh/config"
        )

    if (
        health.total_attempts > 10
        and (health.total_successes / health.total_attempts) < 0.8
    ):
        recommendations.append(
            "Poor success rate detected - consider investigating SSH server logs"
        )
        recommendations.append(
            "May need to reduce concurrent operations or increase timeouts"
        )

    if not os.environ.get("DOCKER_SSH_OPTS"):
        recommendations.append(
            "SSH multiplexing not detected - connection reuse may be limited"
        )

    if not recommendations:
        recommendations.append("SSH connections are working well")

    return recommendations


def _collect_usage_data() -> (
    tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]
):
    """Collect raw data from Docker APIs for disk usage calculation."""
    images_data = _docker_api.images()
    containers_data = _docker_api.containers(all=True)
    volumes_response = _docker_api.volumes()
    volumes_data = volumes_response.get("Volumes", []) if volumes_response else []
    return images_data, containers_data, volumes_data


def _calculate_usage_summary(
    images_data: list[dict[str, Any]],
    containers_data: list[dict[str, Any]],
    volumes_data: list[dict[str, Any]],
) -> dict[str, Any]:
    """Calculate summary statistics for Docker disk usage."""
    # Images calculations
    images_total = len(images_data)
    images_size = sum(img.get("Size", 0) for img in images_data)

    active_image_ids = {
        container["ImageID"] for container in containers_data if "ImageID" in container
    }
    images_active = len(active_image_ids)

    inactive_images_size = sum(
        img.get("Size", 0)
        for img in images_data
        if img.get("Id", "") not in active_image_ids
    )

    # Containers calculations
    containers_total = len(containers_data)
    containers_active = len([c for c in containers_data if c.get("State") == "running"])
    containers_size = sum(c.get("SizeRw", 0) for c in containers_data)

    # Volumes calculations
    volumes_total = len(volumes_data)
    active_volume_names = set()
    for container in containers_data:
        for mount in container.get("Mounts", []):
            if mount.get("Type") == "volume" and mount.get("Name"):
                active_volume_names.add(mount["Name"])
    volumes_active = len(active_volume_names)
    volumes_size = 0  # Would require additional API calls to get actual size

    # Build cache (placeholder values)
    build_cache_total = 0
    build_cache_active = 0
    build_cache_size = 0

    return {
        "type": "summary",
        "data": [
            {
                "type": "Images",
                "total": images_total,
                "active": images_active,
                "size": images_size,
                "reclaimable": inactive_images_size,
                "reclaimable_percent": round(
                    (
                        (inactive_images_size / images_size * 100)
                        if images_size > 0
                        else 0
                    ),
                    1,
                ),
            },
            {
                "type": "Containers",
                "total": containers_total,
                "active": containers_active,
                "size": containers_size,
                "reclaimable": 0,
                "reclaimable_percent": 0,
            },
            {
                "type": "Local Volumes",
                "total": volumes_total,
                "active": volumes_active,
                "size": volumes_size,
                "reclaimable": volumes_size,
                "reclaimable_percent": 100 if volumes_total > volumes_active else 0,
            },
            {
                "type": "Build Cache",
                "total": build_cache_total,
                "active": build_cache_active,
                "size": build_cache_size,
                "reclaimable": build_cache_size,
                "reclaimable_percent": 100,
            },
        ],
    }


def _add_detailed_info(
    summary: dict[str, Any],
    images_data: list[dict[str, Any]],
    containers_data: list[dict[str, Any]],
    volumes_data: list[dict[str, Any]],
) -> None:
    """Add detailed information to the summary for verbose mode."""
    # Detailed images
    detailed_images = []
    for img_data in images_data:
        image_id = img_data.get("Id", "")
        repo_tags = img_data.get("RepoTags") or ["<none>:<none>"]
        created = img_data.get("Created", 0)
        size = img_data.get("Size", 0)
        virtual_size = img_data.get("VirtualSize", 0)

        container_count = sum(
            1 for c in containers_data if c.get("ImageID") == image_id
        )

        for repo_tag in repo_tags:
            repository, tag = (
                repo_tag.rsplit(":", 1) if ":" in repo_tag else (repo_tag, "<none>")
            )
            detailed_images.append(
                {
                    "repository": repository,
                    "tag": tag,
                    "image_id": image_id[:12] if image_id else "",
                    "created": created,
                    "size": size,
                    "shared_size": virtual_size - size if virtual_size > size else 0,
                    "unique_size": size,
                    "containers": container_count,
                }
            )

    # Detailed containers
    detailed_containers = []
    for container_data in containers_data:
        container_id = container_data.get("Id", "")
        image = container_data.get("Image", "")
        command = container_data.get("Command", "")
        if isinstance(command, list) and command:
            command = command[0]

        names = container_data.get("Names", [])
        container_name = (
            names[0][1:]
            if names and names[0].startswith("/")
            else (names[0] if names else "")
        )

        mounts = container_data.get("Mounts", [])
        local_volumes = len([m for m in mounts if m.get("Type") == "volume"])

        detailed_containers.append(
            {
                "container_id": container_id[:12] if container_id else "",
                "image": image,
                "command": command,
                "local_volumes": local_volumes,
                "size": container_data.get("SizeRw", 0),
                "created": container_data.get("Created", 0),
                "status": container_data.get("Status", ""),
                "names": container_name,
            }
        )

    # Detailed volumes
    detailed_volumes = []
    for volume_data in volumes_data:
        volume_name = volume_data.get("Name", "")
        links = sum(
            1
            for container in containers_data
            for mount in container.get("Mounts", [])
            if mount.get("Type") == "volume" and mount.get("Name") == volume_name
        )
        detailed_volumes.append(
            {
                "volume_name": volume_name,
                "links": links,
                "size": 0,
            }
        )

    summary["detailed"] = {
        "images": detailed_images,
        "containers": detailed_containers,
        "volumes": detailed_volumes,
        "build_cache": [],
    }


def _handle_get_docker_disk_usage(args: GetDockerDiskUsageInput) -> dict[str, Any]:
    """Handle get_docker_disk_usage operation to show Docker disk usage."""
    start_time = time.time()
    logger.info(f"💾 Starting get_docker_disk_usage operation with args: {args}")

    try:
        # Collect raw data
        images_data, containers_data, volumes_data = _collect_usage_data()

        # Calculate summary
        summary = _calculate_usage_summary(images_data, containers_data, volumes_data)

        # Add detailed info if requested
        if args.verbose:
            _add_detailed_info(summary, images_data, containers_data, volumes_data)

        total_time = time.time() - start_time
        logger.info(f"🏁 Total get_docker_disk_usage operation took {total_time:.3f}s")

        return summary

    except Exception as e:
        logger.error(f"❌ Error in get_docker_disk_usage: {e}")
        raise e


@app.call_tool()  # type: ignore[misc]
async def call_tool(
    name: str, arguments: Any
) -> Sequence[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    logger.info(f"🔧 MCP Tool Call: {name} with arguments: {arguments}")
    start_time = time.time()

    if arguments is None:
        arguments = {}

    # Define tool handlers mapping
    tool_handlers = [
        _handle_container_tools,
        _handle_image_tools,
        _handle_network_tools,
        _handle_volume_tools,
        _handle_system_tools,
    ]

    try:
        # Try each handler until one returns a result
        for handler in tool_handlers:
            result = handler(name, arguments)
            if result is not None:
                elapsed = time.time() - start_time
                logger.info(f"✅ Tool {name} completed in {elapsed:.3f}s")
                return [
                    types.TextContent(type="text", text=json.dumps(result, indent=2))
                ]

        # If no handler matched, return unknown tool error
        logger.warning(f"❌ Unknown tool: {name}")
        return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

    except ValidationError as e:
        await app.request_context.session.send_log_message(
            "error", "Failed to validate input provided by LLM: " + str(e)
        )
        return [
            types.TextContent(
                type="text", text=f"ERROR: You provided invalid Tool inputs: {e}"
            )
        ]

    except Exception as e:
        await app.request_context.session.send_log_message(
            "error", traceback.format_exc()
        )
        raise e


async def run_stdio(
    settings: ServerSettings, docker_client: docker.DockerClient
) -> None:
    """Run the server on Standard I/O with the given settings and Docker client."""
    from mcp.server.stdio import stdio_server

    global _docker
    _docker = docker_client

    global _docker_api
    _docker_api = docker_client.api

    global _server_settings
    _server_settings = settings

    logger.info("🚀 MCP Docker Server starting up...")
    logger.info(f"📊 Performance settings: Cache limit={_CACHE_SIZE_LIMIT}")
    logger.info(f"🐳 Docker client connected: {docker_client.version()}")

    async with stdio_server() as (read_stream, write_stream):
        logger.info("✅ MCP Docker Server ready to accept requests!")
        logger.info(
            "🔍 Enhanced logging enabled - you should see detailed request logs"
        )
        await app.run(read_stream, write_stream, app.create_initialization_options())
