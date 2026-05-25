ARG PYTHON_BASE_IMAGE=python:3.13.13-slim-bookworm
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.16

FROM ${UV_IMAGE} AS uv_source

# ==============================================================================
# xl-sandboxed-opencode - Hardened Dockerfile
# Base: Minimal Debian with Python 3.13
# ==============================================================================
FROM ${PYTHON_BASE_IMAGE}

ARG HOST_UID=1000
ARG HOST_GID=1000
ARG NODE_MAJOR=22
ARG NODE_VERSION=22.22.2-1nodesource1
ARG OPENCODE_VERSION=1.15.10
ARG GH_VERSION=2.92.0
ARG GH_AMD64_SHA256=8f8212b1a9cec261a8839e0893168f50d3fc70f095da257feef4229234cefdf8
ARG GH_ARM64_SHA256=34d620b7c884774ed86236541535170889fda0b99aafbdab8b69c7d458b5ca6b
ARG TARGETARCH

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    npm_config_audit=false \
    npm_config_fund=false \
    npm_config_update_notifier=false

# 1. System updates, essential tools, sudo, and a signed NodeSource repository.
# opencode-ai uses a postinstall downloader for its platform binary. Keep this
# pinned and build-time only; do not install npm packages at runtime.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    bash-completion \
    bat \
    ca-certificates \
    cloc \
    cmake \
    curl \
    fd-find \
    ffmpeg \
    file \
    git \
    git-lfs \
    gnupg \
    htop \
    iproute2 \
    jq \
    less \
    libgl1 \
    libglib2.0-0 \
    libsndfile1 \
    lsof \
    make \
    nano \
    openssh-client \
    pkg-config \
    procps \
    psmisc \
    ripgrep \
    rsync \
    shellcheck \
    sqlite3 \
    sudo \
    tmux \
    tree \
    unzip \
    vim \
    wget \
    zip \
    && install -d -m 0755 /etc/apt/keyrings \
    && curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key \
        | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg \
    && echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_${NODE_MAJOR}.x nodistro main" \
        > /etc/apt/sources.list.d/nodesource.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends "nodejs=${NODE_VERSION}" \
    && case "${TARGETARCH:-}" in \
        amd64) gh_arch="amd64"; gh_sha="${GH_AMD64_SHA256}" ;; \
        arm64) gh_arch="arm64"; gh_sha="${GH_ARM64_SHA256}" ;; \
        *) echo "Unsupported TARGETARCH '${TARGETARCH:-unset}' for gh install" >&2; exit 1 ;; \
       esac \
    && gh_deb="/tmp/gh_${GH_VERSION}_linux_${gh_arch}.deb" \
    && curl -fsSL "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_${gh_arch}.deb" -o "${gh_deb}" \
    && echo "${gh_sha}  ${gh_deb}" | sha256sum -c - \
    && apt-get install -y --no-install-recommends "${gh_deb}" \
    && npm install -g --omit=dev "opencode-ai@${OPENCODE_VERSION}" \
    && npm cache clean --force \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /tmp/*

# Add the agent package allowlist and constrained sudo rules.
COPY config/apt-package-allowlist.txt /tmp/apt-package-allowlist.txt
COPY scripts/agent-apt-install /usr/local/sbin/agent-apt-install
COPY scripts/agent-kill-port /usr/local/sbin/agent-kill-port
RUN install -d -m 0755 /etc/agent \
    && mv /tmp/apt-package-allowlist.txt /etc/agent/apt-package-allowlist.txt \
    && chown root:root /etc/agent/apt-package-allowlist.txt /usr/local/sbin/agent-apt-install /usr/local/sbin/agent-kill-port \
    && chmod 0444 /etc/agent/apt-package-allowlist.txt \
    && chmod 0755 /usr/local/sbin/agent-apt-install /usr/local/sbin/agent-kill-port \
    && echo "agent ALL=(root) NOPASSWD: /usr/local/sbin/agent-apt-install *, /usr/local/sbin/agent-kill-port *" > /etc/sudoers.d/agent-apt \
    && chmod 0440 /etc/sudoers.d/agent-apt

# 2. Securely install 'uv' directly from the official Astral image
COPY --from=uv_source /uv /uvx /bin/

# 3. Create non-root agent user matching the host
# If the GID already exists (e.g., GID 20), we use it. Otherwise, we create it.
RUN getent group ${HOST_GID} || groupadd -g ${HOST_GID} agent_group
RUN useradd -m -u ${HOST_UID} -g ${HOST_GID} -s /bin/bash agent

# 4. Set up the workspace directories
RUN mkdir -p /home/agent/projects \
             /home/agent/shared \
             /home/agent/temp/cache \
             /home/agent/app \
    && chown -R agent:${HOST_GID} /home/agent

# 6. Copy the entrypoint script (using just 'agent' defaults to their primary group)
COPY --chown=agent entrypoint.sh /home/agent/app/entrypoint.sh
COPY --chown=agent scripts/monitor-ports.sh /home/agent/app/monitor-ports.sh
COPY --chown=agent scripts/monitor-resources.sh /home/agent/app/monitor-resources.sh
COPY --chown=agent scripts/monitor-logs.sh /home/agent/app/monitor-logs.sh
COPY --chown=agent scripts/dashboard.py /home/agent/app/dashboard.py
COPY --chown=agent scripts/dashboard-server.sh /home/agent/app/dashboard-server.sh
COPY --chown=agent scripts/mcp-bridge.py /home/agent/app/mcp-bridge.py
RUN chmod +x /home/agent/app/entrypoint.sh /home/agent/app/monitor-*.sh /home/agent/app/dashboard-server.sh

# 7. Lock down the container to the non-root user
USER agent
WORKDIR /home/agent/projects

# 8. Entrypoint execution
STOPSIGNAL SIGTERM
ENTRYPOINT ["/home/agent/app/entrypoint.sh"]
