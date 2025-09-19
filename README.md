# 🐋 mcp-docker-server

[![PyPI - Version](https://img.shields.io/pypi/v/mcp-docker-server)](https://pypi.org/project/mcp-docker-server/)
[![GitHub release (latest SemVer)](https://img.shields.io/github/v/release/pnmice/mcp-docker-server?sort=semver)](https://github.com/pnmice/mcp-docker-server/releases/latest)
[![Build](https://github.com/pnmice/mcp-docker-server/actions/workflows/deploy.yml/badge.svg)](https://github.com/pnmice/mcp-docker-server/actions/workflows/deploy.yml)
[![codecov](https://codecov.io/gh/pnmice/mcp-docker-server/branch/master/graph/badge.svg)](https://codecov.io/gh/pnmice/mcp-docker-server "Non-generated packages only")

**Effortlessly orchestrate and oversee Docker environments from anywhere, using natural, conversational commands.**

mcp-docker-server is an open-source MCP (Model Context Protocol) server that transforms Docker container management by bridging the gap between human intuition and automation. Built for DevOps professionals who demand both power and simplicity.

## 🎯 Core Capabilities

- **🗣️ Natural Language Orchestration**: Compose multi-container environments using conversational commands
- **🔗 Remote SSH Management**: Securely manage Docker environments across local and remote infrastructure
- **🔍 Intelligent Debugging**: Introspect running containers with AI-assisted troubleshooting
- **📊 Unified Observability**: Monitor container stats, logs, and resource usage from a single interface
- **⚡ Automation-Ready**: Integrate with CI/CD pipelines and infrastructure-as-code workflows

## 👥 Built for DevOps Professionals

**DevOps Engineers & SREs**: Reduce cognitive load when managing complex container environments. Replace fragmented toolchains with unified, conversational control.

**Cloud Architects & Consultants**: Demonstrate rapid prototyping and environment setup to clients. Manage multiple client infrastructures with consistent, intuitive commands.

**Open Source Contributors**: Contribute to a tool that democratizes infrastructure automation. Help build the future of developer-friendly container management.

**Scale-up Teams**: Accelerate development velocity without sacrificing operational reliability. Perfect for teams transitioning from manual processes to automated infrastructure.

## 🚀 Quick Start

### Prerequisites

- **Docker**: Ensure Docker is running locally or accessible via SSH
- **Python 3.11+**: Required for the MCP server
- **Claude Desktop or Claude Code**: For natural language interaction

### Installation

#### Option 1: Direct Installation with uv (Recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh
# or: brew install uv

# Install mcp-docker-server
uvx mcp-docker-server
```

#### Option 2: Install from PyPI

```bash
pip install mcp-docker-server
```

#### Option 3: Install from Test PyPI (Testing/Preview versions)

```bash
# Install from Test PyPI with PyPI fallback for dependencies
pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ mcp-docker-server
```

#### Option 4: Development Installation

```bash
git clone https://github.com/pnmice/mcp-docker-server
cd mcp-docker-server
uv tool install .

# Force reinstall after updates
uv tool install --force --reinstall .
```

### Configuration

#### Claude code

MacOS (with Docker Desktop):

Claude Code configuration:
```
claude mcp add mcp-docker-server --env DOCKER_HOST=unix:///Users/youruser/.docker/run/docker.sock -- uvx mcp-docker-server
```
Codex configuration:
```
cat ~/.codex/config.toml
[mcp_servers.mcp-docker-server]
command = "uvx"
args = ["mcp-docker-server"]
```

Claude Code configuration:
```
claude mcp add mcp-docker-server -- uvx mcp-docker-server
```

Codex configuration:
```
cat ~/.codex/config.toml
[mcp_servers.mcp-docker-server]
command = "uvx"
args = ["mcp-docker-server"]
```

Support ~/.ssh/config aliases:

Claude Code configuration:
```
claude mcp add mcp-docker-server-alias --env DOCKER_HOST=ssh://your-ssh-config-alias -- uvx mcp-docker-server
```

Codex configuration:
```
cat ~/.codex/config.toml
[mcp_servers.mcp-docker-server-alias]
command = "uvx"
args = ["mcp-docker-server"]
env = { DOCKER_HOST = "ssh://your-ssh-config-alias" }
``` 

#### Claude Desktop

<details>
  <summary>Claude Desktop Configuration</summary>

On MacOS: `~/Library/Application\ Support/Claude/claude_desktop_config.json`

On Windows: `%APPDATA%/Claude/claude_desktop_config.json`

Then add the following to your MCP servers file:

```json
{
  "mcpServers": {
    "mcp-docker-server": {
      "command": "uvx",
      "args": [
        "mcp-docker-server"
      ]
    }
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

```json
{
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

### Monitoring

- `get_docker_disk_usage`
- `get_container_stats`

## 🚧 Security & Best Practices

### Sensitive Data

**DO NOT CONFIGURE CONTAINERS WITH SENSITIVE DATA.** This includes API keys,
database passwords, etc.

Any sensitive data exchanged with the LLM is inherently compromised, unless the
LLM is running on your local machine.

If you are interested in securely passing secrets to containers, file an issue
on this repository with your use-case.

## 🛠️ Configuration

This server uses the Python Docker SDK's `from_env` method. For configuration
details, see [the documentation](https://docker-py.readthedocs.io/en/stable/client.html#docker.client.from_env).

### Connect to Docker over SSH

This MCP server can connect to a remote Docker daemon over SSH.

#### Using full SSH URLs

Set a `ssh://` host URL with username and hostname in the MCP server definition:

```json
{
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
}
```

#### Using SSH config aliases

You can also use SSH config aliases defined in your `~/.ssh/config` file:

```json
{
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
}
```

The server will automatically resolve SSH config aliases to their full connection details (hostname, username, port) from your SSH configuration.

## 💻 Development

Build docker image for development:

```
docker build -t mcp-docker-server:dev -f Dockerfile.dev .
```

Run the development container:

```
mv env.example .env
# replace your ssh config alias in .env
# DOCKER_HOST=ssh://your-ssh-config-alias
docker-compose -f docker-compose.dev.yaml up -d --build
```

Local development with Docker:

Claude Code configuration:
```
claude mcp add mcp-docker-server-dev --env DOCKER_HOST=unix:///Users/user/.docker/run/docker.sock -- docker run -i --rm -v /var/run/docker.sock:/var/run/docker.sock mcp-docker-server:dev mcp-run
```

Codex configuration:
```
cat ~/.codex/config.toml  

[mcp_servers.mcp-docker-server-dev]
command = "docker"
args = ["run", "-i", "--rm", "-v", "/var/run/docker.sock:/var/run/docker.sock", "mcp-docker-server:dev", "mcp-run"]
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

Claude Code configuration:
```
claude mcp add mcp-docker-server-dev -- docker exec -i mcp-docker-server-dev mcp-run
```

Codex configuration:
```
cat ~/.codex/config.toml

[mcp_servers.mcp-docker-server-dev]
command = "docker"
args = ["exec", "-i", "mcp-docker-server-dev", "mcp-run"]
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

## 🌟 Contributing to the Future of DevOps

mcp-docker-server is more than a tool—it's a step toward democratizing infrastructure automation. Built with the belief that powerful DevOps capabilities should be accessible, intuitive, and secure for all practitioners.

### 🤝 Get Involved

- **Report Issues**: Share your real-world use cases and pain points
- **Contribute Code**: Help build features that matter to the DevOps community  
- **Share Knowledge**: Write about your experiences and help others learn
- **Spread the Word**: Help fellow DevOps engineers discover better ways to work

### 💡 Vision

We're building toward a future where automation, AI, and resilient infrastructure empower every technologist to build, experiment, and scale with confidence—breaking down barriers between creativity and operational excellence.

---

*Built with ❤️ for the DevOps community*