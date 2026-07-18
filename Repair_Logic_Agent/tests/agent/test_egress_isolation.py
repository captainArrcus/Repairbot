"""Feature 2.5 (spec D8) — egress isolation verification.

Docker-gated: needs the worker image built and the proxy/network up:
    docker compose -f infra/docker-compose.agent.yml up -d egress-proxy
    docker compose -f infra/docker-compose.agent.yml build agent-worker
"""

import shutil
import subprocess

import pytest

IMAGE = "repair-agent-worker"
NETWORK = "repair-agent_internal"
PROXY = "http://egress-proxy:3128"


def _docker_ready() -> bool:
    if not shutil.which("docker"):
        return False
    image = subprocess.run(["docker", "image", "inspect", IMAGE], capture_output=True)
    network = subprocess.run(["docker", "network", "inspect", NETWORK], capture_output=True)
    proxy = subprocess.run(
        ["docker", "ps", "--filter", "name=egress-proxy", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
    )
    return image.returncode == 0 and network.returncode == 0 and "egress-proxy" in proxy.stdout


needs_docker = pytest.mark.skipif(
    not _docker_ready(),
    reason="agent image/network/proxy not up (docker compose -f infra/docker-compose.agent.yml)",
)


def _run_in_container(code: str, env: dict | None = None) -> subprocess.CompletedProcess:
    cmd = ["docker", "run", "--rm", "--network", NETWORK]
    for key, value in (env or {}).items():
        cmd += ["-e", f"{key}={value}"]
    cmd += [IMAGE, "python", "-c", code]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=90)


@needs_docker
def test_direct_egress_fails():
    # internal network = no default route; without the proxy nothing gets out
    result = _run_in_container("import httpx; httpx.get('https://example.com', timeout=8)")
    assert result.returncode != 0


@needs_docker
def test_proxy_blocks_non_allowlisted_host():
    result = _run_in_container(
        "import httpx; r = httpx.get('https://example.com', timeout=15);"
        " assert r.status_code < 400, r.status_code",
        env={"HTTPS_PROXY": PROXY},
    )
    assert result.returncode != 0  # squid denies the CONNECT


@needs_docker
def test_proxy_allows_llm_endpoint():
    result = _run_in_container(
        "import httpx;"
        " r = httpx.get('https://generativelanguage.googleapis.com/', timeout=20);"
        " print(r.status_code)",
        env={"HTTPS_PROXY": PROXY},
    )
    assert result.returncode == 0, result.stderr
