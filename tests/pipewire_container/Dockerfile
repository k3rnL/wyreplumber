FROM python:3.12-slim-trixie

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install PipeWire and required dependencies
RUN apt-get update && apt-get install -y \
    pipewire wireplumber \
    pipewire-bin \
    libpipewire-0.3-dev \
    libwireplumber-0.5-dev \
    pkg-config \
    gcc \
    dbus \
    && rm -rf /var/lib/apt/lists/*

# Copy config
COPY ./config/* /usr/share/pipewire/

COPY ./wireplumber.conf /etc/wireplumber/wireplumber.conf.d/access.conf
COPY ./wireplumber.conf /usr/share/wireplumber/wireplumber.conf.d/access.conf

# Set up runtime directory
ENV XDG_RUNTIME_DIR=/run/user/1000

# Start PipeWire and run tests
CMD ["pipewire"]
