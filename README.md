# 🐋 Docker MCP server

An MCP server for managing Docker with natural language!

## 🪩 What can it do?

- 🚀 Compose containers with natural language
- 🔍 Introspect & debug running containers
- 📀 Manage persistent data with Docker volumes

## ❓ Who is this for?

- Server administrators: connect to remote Docker engines for e.g. managing a
  public-facing website.
- Tinkerers: run containers locally and experiment with open-source apps
  supporting Docker.
- AI enthusiasts: push the limits of that an LLM is capable of!

## 🏎️ Quickstart



### Install

```
pip install uv
```

```
brew install uv
```

```
cd mcp-docker-server
uv tool install .
```

Forcing a reinstall (e.g. after pulling new changes):
```
uv tool install --force --reinstall .
```

If you don't have `uv` installed, follow the installation instructions for your system:

[link](https://docs.astral.sh/uv/getting-started/installation/#installation-methods)

#### Claude code

MacOS (with Docker Desktop):
```
claude mcp add mcp-docker-server --env DOCKER_HOST=unix:///Users/youruser/.docker/run/docker.sock -- uvx mcp-docker-server
```

```
claude mcp add mcp-docker-server -- uvx mcp-docker-server
```

Support ~/.ssh/config aliases:
```
claude mcp add mcp-docker-server-shainy --env DOCKER_HOST=ssh://your-ssh-config-alias -- uvx mcp-docker-server
```

#### Claude Desktop

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`

On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

Then add the following to your MCP servers file:

```
"mcpServers": {
  "mcp-docker-server": {
    "command": "uvx",
    "args": [
      "mcp-docker-server"
    ]
  }
}
```

</details>

<details>
  <summary>Install with Docker</summary>

Purely for convenience, the server can run in a Docker container.

After cloning this repository, build the Docker image:

```bash
docker build -t mcp-docker-server .
```

And then add the following to your MCP servers file:

```
"mcpServers": {
  "mcp-docker-server": {
    "command": "docker",
    "args": [
      "run",
      "-i",
      "--rm",
      "-v",
      "/var/run/docker.sock:/var/run/docker.sock",
      "mcp-docker-server:latest"
    ]
  }
}
```

Note that we mount the Docker socket as a volume; this ensures the MCP server
can connect to and control the local Docker daemon.

</details>

## 📝 Prompts

### 🎻 `docker_compose`

Use natural language to compose containers.

Provide a Project Name, and a description of desired containers, and let the LLM
do the rest.

This prompt instructs the LLM to enter a `plan+apply` loop. Your interaction
with the LLM will involve the following steps:

1. You give the LLM instructions for which containers to bring up
2. The LLM calculates a concise natural language plan and presents it to you
3. You either:
   - Apply the plan
   - Provide the LLM feedback, and the LLM recalculates the plan

#### Examples

- name: `nginx`, containers: "deploy an nginx container exposing it on port
  9000"
- name: `wordpress`, containers: "deploy a WordPress container and a supporting
  MySQL container, exposing Wordpress on port 9000"

#### Resuming a Project

When starting a new chat with this prompt, the LLM will receive the status of
any containers, volumes, and networks created with the given project `name`.

This is mainly useful for cleaning up, in-case you lose a chat that was
responsible for many containers.

## 📔 Resources

The server implements a couple resources for every container:

- Stats: CPU, memory, etc. for a container
- Logs: tail some logs from a container

## 🔨 Tools

### Containers

- `list_containers`
- `create_container`
- `run_container`
- `recreate_container`
- `start_container`
- `fetch_container_logs`
- `stop_container`
- `remove_container`

### Images

- `list_images`
- `pull_image`
- `push_image`
- `build_image`
- `remove_image`

### Networks

- `list_networks`
- `create_network`
- `remove_network`

### Volumes

- `list_volumes`
- `create_volume`
- `remove_volume`

## 🚧 Disclaimers

### Sensitive Data

**DO NOT CONFIGURE CONTAINERS WITH SENSITIVE DATA.** This includes API keys,
database passwords, etc.

Any sensitive data exchanged with the LLM is inherently compromised, unless the
LLM is running on your local machine.

If you are interested in securely passing secrets to containers, file an issue
on this repository with your use-case.

### Reviewing Created Containers

Be careful to review the containers that the LLM creates. Docker is not a secure
sandbox, and therefore the MCP server can potentially impact the host machine
through Docker.

For safety reasons, this MCP server doesn't support sensitive Docker options
like `--privileged` or `--cap-add/--cap-drop`. If these features are of interest
to you, file an issue on this repository with your use-case.

## 🛠️ Configuration

This server uses the Python Docker SDK's `from_env` method. For configuration
details, see
[the documentation](https://docker-py.readthedocs.io/en/stable/client.html#docker.client.from_env).

### Connect to Docker over SSH

This MCP server can connect to a remote Docker daemon over SSH.

#### Using full SSH URLs

Set a `ssh://` host URL with username and hostname in the MCP server definition:

```
"mcpServers": {
  "mcp-docker-server": {
    "command": "uvx",
    "args": [
      "mcp-docker-server"
    ],
    "env": {
      "DOCKER_HOST": "ssh://myusername@myhost.example.com"
    }
  }
}
```

#### Using SSH config aliases

You can also use SSH config aliases defined in your `~/.ssh/config` file:

```
"mcpServers": {
  "mcp-docker-server": {
    "command": "uvx",
    "args": [
      "mcp-docker-server"
    ],
    "env": {
      "DOCKER_HOST": "ssh://your-ssh-config-alias"
    }
  }
}
```

The server will automatically resolve SSH config aliases to their full connection details (hostname, username, port) from your SSH configuration.

## 💻 Development

Local development with Docker:

```
claude mcp add mcp-docker-server-dev --env DOCKER_HOST=unix:///Users/user/.docker/run/docker.sock -- docker run -i --rm -v /var/run/docker.sock:/var/run/docker.sock mcp-docker-server:dev mcp-run
```

Remote development with Docker over SSH:

MacOs (with Docker Desktop):

```
brew install socat

mkdir -p ~/.ssh

# Kill any old relay
[ -f ~/.ssh/agent-relay.pid ] && kill "$(cat ~/.ssh/agent-relay.pid)" 2>/dev/null || true
rm -f ~/.ssh/agent.sock

# Start the relay (background)
nohup socat UNIX-LISTEN:$HOME/.ssh/agent.sock,fork,mode=600 \
             UNIX-CONNECT:"$SSH_AUTH_SOCK" \
      >/tmp/ssh-agent-relay.log 2>&1 &
echo $! > ~/.ssh/agent-relay.pid
```

```
docker-compose -f docker-compose.dev.yaml up -d --build
```

```
claude mcp add mcp-docker-server-dev -- docker exec -i mcp-docker-server-dev mcp-run
```

## Testing

Run tests with:

```
pytest
# or
pytest -v
``` 

For coverage report:

```
pytest --cov=src/mcp_docker_server --cov-report=term-missing
```

Run tests by category:

```
pytest -m unit
# or
pytest -m unit --tb=short
```

```
pytest -m integration
```

Run specific test file:

```
pytest tests/test_handlers.py
```

```
pytest src/tests/test_handlers.py::TestContainerHandlers
```

```
pytest src/tests/test_handlers.py::TestContainerHandlers::test_list_containers
```

Testing with Coverage:

Run with coverage and generate HTML report

```
pytest --cov=src/mcp_docker_server --cov-report=html
```

Fail if coverage is below 85%

```
pytest --cov=src/mcp_docker_server --cov-fail-under=85
```