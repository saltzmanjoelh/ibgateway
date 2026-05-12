# Build for x64 (linux/amd64) architecture to support IB Gateway:
#   docker build --platform linux/amd64 -t ibgateway .
# IB Gateway requires x86_64 architecture, so use --platform linux/amd64 when building
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV USER=root
ENV RESOLUTION=1024x768

# 1. Install noVNC and Websockify
RUN apt-get update && apt-get install -y x11vnc git python3 python3-pip tcpdump && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*
RUN mkdir -p /opt/novnc
RUN git clone https://github.com/novnc/noVNC.git /opt/novnc
RUN git clone https://github.com/novnc/websockify /opt/novnc/utils/websockify
RUN ln -s /opt/novnc/vnc.html /opt/novnc/index.html
RUN cd /opt/novnc/utils/websockify && pip3 install .

# 2. Copy CLI package and Poetry configuration, then install Python dependencies
COPY ibgateway_manager/ /ibgateway_manager/
COPY ibgateway_manager_cli.py /ibgateway_manager_cli.py
COPY pyproject.toml /pyproject.toml
COPY poetry.lock /poetry.lock
COPY test-screenshots/ /test-screenshots/

# 3. Update and install basic tools + Xvfb and Install Poetry
COPY scripts/setup.sh /scripts/setup.sh
RUN chmod +x /scripts/setup.sh
RUN ./scripts/setup.sh && apt-get autoremove -y && rm -rf /var/lib/apt/lists/*

# 4. Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 5900 noVNC, 8080 screenshot HTTP server, 8090 MCP server (Streamable HTTP),
# 4003/4004 IB API live/paper, 5678 debugpy
EXPOSE 5900 8080 8090 4003 4004 5678

HEALTHCHECK --start-period=180s --interval=10s --timeout=2s --retries=1 \
  CMD python3 -m ibgateway_manager.healthcheck

CMD ["/entrypoint.sh"]

# docker run --platform linux/amd64 -v $(pwd)/automate-ibgateway.sh:/automate-ibgateway.sh -p 5900:5900 -it --rm ubuntu-novnc
