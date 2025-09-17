import json
from datetime import datetime
from typing import Any, Literal, get_args, get_origin

from pydantic import (
    BaseModel,
    Field,
    ValidationInfo,
    computed_field,
    field_validator,
    model_validator,
)


class JSONParsingModel(BaseModel):
    """
    A base Pydantic model that attempts to parse JSON strings for non-primitive fields.
    If a string is provided for a field that expects a complex type (dict, list, or another model),
    it will attempt to parse it as JSON.

    Claude appears to not understand that a nested field shouldn't be a JSON-encoded string...
    But it does send valid JSON!
    """

    @field_validator("*", mode="before")
    @classmethod
    def _try_parse_json(cls, value: Any, info: ValidationInfo) -> Any:
        if not isinstance(value, str):
            return value

        fields = cls.model_fields
        field_name = info.field_name

        if field_name not in fields:
            return value

        field = fields[field_name]
        field_type = field.annotation

        # Handle Optional/Union types
        origin = get_origin(field_type)
        if origin is not None:
            args = get_args(field_type)
            # Find the non-None type in case of Optional
            field_type = next(
                (arg for arg in args if arg is not type(None)), field_type
            )

        # Don't try to parse strings, numbers, or dates
        if field_type in (str, int, float, bool, datetime):
            return value

        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return value


class FetchContainerLogsInput(JSONParsingModel):
    container_id: str = Field(..., description="Container ID or name")
    tail: int | Literal["all"] = Field(
        100, description="Number of lines to show from the end"
    )
    grep: str | None = Field(
        None, description="Filter logs by pattern (case-insensitive grep-like search)"
    )
    since: str | None = Field(
        None,
        description="Show logs since timestamp (e.g. 2013-01-02T13:23:37Z) or relative (e.g. 42m for 42 minutes)",
    )
    until: str | None = Field(
        None,
        description="Show logs until timestamp (e.g. 2013-01-02T13:23:37Z) or relative (e.g. 42m for 42 minutes)",
    )


class ListContainersFilters(JSONParsingModel):
    label: list[str] | None = Field(
        None, description="Filter by label, either `key` or `key=value` format"
    )
    status: list[str] | None = Field(
        None,
        description="Filter by status (created, restarting, running, removing, paused, exited, dead)",
    )
    name: list[str] | None = Field(None, description="Filter by container name")
    id: list[str] | None = Field(None, description="Filter by container ID")
    ancestor: list[str] | None = Field(
        None, description="Filter by image name/ID that created the container"
    )


class ListContainersInput(JSONParsingModel):
    all: bool = Field(
        False, description="Show all containers (default shows just running)"
    )
    filters: ListContainersFilters | None = Field(None, description="Filter containers")
    limit: int | None = Field(
        100,
        description="Maximum number of containers to return (default: 100, max: 1000). Set to 0 for no limit (use with caution).",
        ge=0,
        le=1000,
    )


class CreateContainerInput(JSONParsingModel):
    """
    Schema for creating a new container.

    This is passed to the Python Docker SDK directly, so the fields are the same
    as the `docker.containers.create` method.
    """

    detach: bool = Field(
        True,
        description="Run container in the background. Should be True for long-running containers, can be false for short-lived containers",
    )
    image: str = Field(..., description="Docker image name")
    name: str | None = Field(None, description="Container name")
    entrypoint: str | None = Field(None, description="Entrypoint to run in container")
    command: str | None = Field(None, description="Command to run in container")
    network: str | None = Field(None, description="Network to attach the container to")
    environment: dict[str, str] | None = Field(
        None, description="Environment variables dictionary"
    )
    ports: dict[str, int | list[int] | tuple[str, int] | None] | None = Field(
        None,
        description="A map whose keys are the container port, and the values are the host port(s) to bind to.",
    )
    volumes: dict[str, dict[str, str]] | list[str] | None = Field(
        None, description="Volume mappings"
    )
    labels: dict[str, str] | list[str] | None = Field(
        None,
        description="Container labels, either as a dictionary or a list of key=value strings",
    )
    auto_remove: bool = Field(False, description="Automatically remove the container")


class RecreateContainerInput(CreateContainerInput):
    container_id: str | None = Field(
        None,
        description="Container ID to recreate. The `name` parameter will be used if this is not provided",
    )

    @computed_field
    def resolved_container_id(self) -> str:
        return (
            self.container_id or self.name or ""
        )  # One of these will be non-None after validation

    @model_validator(mode="after")
    def validate_container_id(self) -> "RecreateContainerInput":
        if self.container_id is None and self.name is None:
            raise ValueError(
                "container_id or name is required for identifying the container to stop+remove"
            )
        return self


class ContainerActionInput(JSONParsingModel):
    container_id: str = Field(..., description="Container ID or name")


class RemoveContainerInput(JSONParsingModel):
    container_id: str = Field(..., description="Container ID or name")
    force: bool = Field(False, description="Force remove the container")


class ListImagesFilters(JSONParsingModel):
    dangling: bool | None = Field(None, description="Show dangling images")
    label: list[str] | None = Field(
        None, description="Filter by label, either `key` or `key=value` format"
    )


class ListImagesInput(JSONParsingModel):
    name: str | None = Field(
        None, description="Filter images by repository name, if desired"
    )
    all: bool = Field(False, description="Show all images (default hides intermediate)")
    filters: ListImagesFilters | None = Field(None, description="Filter images")


class PullPushImageInput(JSONParsingModel):
    repository: str = Field(..., description="Image repository")
    tag: str | None = Field("latest", description="Image tag")


class BuildImageInput(JSONParsingModel):
    path: str = Field(..., description="Path to build context")
    tag: str = Field(..., description="Image tag")
    dockerfile: str | None = Field(None, description="Path to Dockerfile")


class RemoveImageInput(JSONParsingModel):
    image: str = Field(..., description="Image ID or name")
    force: bool = Field(False, description="Force remove the image")


class ListNetworksFilter(JSONParsingModel):
    label: list[str] | None = Field(
        None, description="Filter by label, either `key` or `key=value` format"
    )


class ListNetworksInput(JSONParsingModel):
    filters: ListNetworksFilter | None = Field(None, description="Filter networks")


class CreateNetworkInput(JSONParsingModel):
    name: str = Field(..., description="Network name")
    driver: str | None = Field("bridge", description="Network driver")
    internal: bool = Field(False, description="Create an internal network")
    labels: dict[str, str] | None = Field(None, description="Network labels")


class RemoveNetworkInput(JSONParsingModel):
    network_id: str = Field(..., description="Network ID or name")


class ListVolumesInput(JSONParsingModel):
    pass


class CreateVolumeInput(JSONParsingModel):
    name: str = Field(..., description="Volume name")
    driver: str | None = Field("local", description="Volume driver")
    labels: dict[str, str] | None = Field(None, description="Volume labels")


class RemoveVolumeInput(JSONParsingModel):
    volume_name: str = Field(..., description="Volume name")
    force: bool = Field(False, description="Force remove the volume")


class GetDockerDiskUsageInput(JSONParsingModel):
    verbose: bool = Field(False, description="Show detailed information on space usage")


class GetContainerStatsInput(JSONParsingModel):
    containers: list[str] | None = Field(
        None,
        description="List of container IDs or names to get stats for. If None, gets stats for all running containers",
    )
    all: bool = Field(
        False, description="Show stats for all containers (default shows just running)"
    )


class DockerComposePromptInput(BaseModel):
    name: str
    containers: str
