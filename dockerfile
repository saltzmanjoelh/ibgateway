# Build for x64 (linux/amd64) architecture to support IB Gateway:
#   docker build --platform linux/amd64 -t ibgateway .
# IB Gateway requires x86_64 architecture, so use --platform linux/amd64 when building
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV USER=root
ENV RESOLUTION=1024x768

# 1. Update and install basic tools + Xvfb + VNC
RUN apt-get update && apt-get install -y \
    xvfb \
    x11vnc \
    xterm \
    dbus-x11 \
    git \
    python3 \
    python3-pip \
    python3-numpy \
    net-tools \
    curl \
    xdotool \
    wmctrl \
    scrot \
    imagemagick \
    socat \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# 2. Install noVNC and Websockify
RUN mkdir -p /opt/novnc \
    && git clone https://github.com/novnc/noVNC.git /opt/novnc \
    && git clone https://github.com/novnc/websockify /opt/novnc/utils/websockify \
    && ln -s /opt/novnc/vnc.html /opt/novnc/index.html \
    && cd /opt/novnc/utils/websockify && pip3 install .

# 3. Copy CLI package and requirements, then install Python dependencies
COPY ibgateway/ /ibgateway/
COPY ibgateway_cli.py /ibgateway_cli.py
COPY requirements.txt /requirements.txt
RUN pip3 install --no-cache-dir -r /requirements.txt && \
    chmod +x /ibgateway_cli.py

# 4. Install IB Gateway using CLI tool
RUN python3 /ibgateway_cli.py install

# 5. Copy entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 5900 8080 4003 4004

CMD ["/entrypoint.sh"]

# docker run --platform linux/amd64 -v $(pwd)/automate-ibgateway.sh:/automate-ibgateway.sh -p 5900:5900 -it --rm ubuntu-novnc