# Build for x64 (linux/amd64) architecture to support IB Gateway:
#   docker build --platform linux/amd64 -t ibgateway .
# IB Gateway requires x86_64 architecture, so use --platform linux/amd64 when building
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV USER=root
ENV RESOLUTION=1280x800

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
    python3-tk \
    net-tools \
    curl \
    xdotool \
    wmctrl \
    scrot \
    imagemagick \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# 2. Install noVNC and Websockify
RUN mkdir -p /opt/novnc \
    && git clone https://github.com/novnc/noVNC.git /opt/novnc \
    && git clone https://github.com/novnc/websockify /opt/novnc/utils/websockify \
    && ln -s /opt/novnc/vnc.html /opt/novnc/index.html \
    && cd /opt/novnc/utils/websockify && pip3 install .

COPY install-ibgateway.sh /install-ibgateway.sh
RUN chmod +x /install-ibgateway.sh && sh /install-ibgateway.sh && rm -f /install-ibgateway.sh
# 3. Add script to run IB Gateway under Xvfb for headless operation
COPY run-ibgateway.sh /run-ibgateway.sh
RUN chmod +x /run-ibgateway.sh 

COPY automate-ibgateway.sh /automate-ibgateway.sh
RUN chmod +x /automate-ibgateway.sh

# 4. Copy scripts (can be overridden with volume mounts at runtime)
# To update scripts without rebuilding, mount them as volumes:
#   docker run -v $(pwd)/entrypoint.sh:/entrypoint.sh -v $(pwd)/install-ibgateway.sh:/install-ibgateway.sh ...
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY screenshot-service.sh /screenshot-service.sh
RUN chmod +x /screenshot-service.sh

COPY screenshot-server.py /screenshot-server.py
RUN chmod +x /screenshot-server.py

COPY draw-square-on-screen.py /draw-square-on-screen.py
RUN chmod +x /draw-square-on-screen.py

EXPOSE 5900 8080

CMD ["/entrypoint.sh"]

# docker run --platform linux/amd64 -v $(pwd)/automate-ibgateway.sh:/automate-ibgateway.sh -p 5900:5900 -it --rm ubuntu-novnc