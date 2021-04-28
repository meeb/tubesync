FROM debian:buster-slim

ARG ARCH="amd64"
ARG S6_VERSION="2.2.0.3"
ARG FFMPEG_VERSION="4.3.2"

ENV DEBIAN_FRONTEND="noninteractive" \
    HOME="/root" \
    LANGUAGE="en_US.UTF-8" \
    LANG="en_US.UTF-8" \
    LC_ALL="en_US.UTF-8" \
    TERM="xterm" \
    S6_EXPECTED_SHA256="a7076cf205b331e9f8479bbb09d9df77dbb5cd8f7d12e9b74920902e0c16dd98" \
    S6_DOWNLOAD="https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-${ARCH}.tar.gz" \
    FFMPEG_EXPECTED_SHA256="34bffcd0b58695e3ee5eba2573b37f06cb5088050733ca96265815f58bd61d35" \
    FFMPEG_DOWNLOAD="https://tubesync.sfo2.digitaloceanspaces.com/ffmpeg-${FFMPEG_VERSION}-${ARCH}-static.tar.xz"


# Install third party software
RUN set -x && \
    apt-get update && \
    apt-get -y --no-install-recommends install locales && \
    echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && \
    locale-gen en_US.UTF-8 && \
    # Install required distro packages
    apt-get -y --no-install-recommends install curl xz-utils ca-certificates binutils && \
    # Install s6
    curl -L ${S6_DOWNLOAD} --output /tmp/s6-overlay-${ARCH}.tar.gz && \
    sha256sum /tmp/s6-overlay-${ARCH}.tar.gz && \
    echo "${S6_EXPECTED_SHA256}  /tmp/s6-overlay-${ARCH}.tar.gz" | sha256sum -c - && \
    tar xzf /tmp/s6-overlay-${ARCH}.tar.gz -C / && \
    # Install ffmpeg
    curl -L ${FFMPEG_DOWNLOAD} --output /tmp/ffmpeg-${ARCH}-static.tar.xz && \
    echo "${FFMPEG_EXPECTED_SHA256}  /tmp/ffmpeg-${ARCH}-static.tar.xz" | sha256sum -c - && \
    xz --decompress /tmp/ffmpeg-${ARCH}-static.tar.xz && \
    tar -xvf /tmp/ffmpeg-${ARCH}-static.tar -C /tmp && \
    install -v -s -g root -o root -m 0755 -s /tmp/ffmpeg-${FFMPEG_VERSION}-${ARCH}-static/ffmpeg -t /usr/local/bin && \
    # Clean up
    rm -rf /tmp/s6-overlay-${ARCH}.tar.gz && \
    rm -rf /tmp/ffmpeg-${ARCH}-static.tar && \
    rm -rf /tmp/ffmpeg-${FFMPEG_VERSION}-${ARCH}-static && \
    apt-get -y autoremove --purge curl xz-utils binutils

# Copy app
COPY tubesync /app
COPY tubesync/tubesync/local_settings.py.container /app/tubesync/local_settings.py

# Append container bundled software versions
RUN echo "ffmpeg_version = '${FFMPEG_VERSION}-static'" >> /app/common/third_party_versions.py

# Add Pipfile
COPY Pipfile /app/Pipfile
COPY Pipfile.lock /app/Pipfile.lock

# Switch workdir to the the app
WORKDIR /app

# Set up the app
RUN set -x && \
  apt-get update && \
  # Install required distro packages
  apt-get -y install nginx-light && \
  apt-get -y --no-install-recommends install python3 python3-setuptools python3-pip python3-dev gcc make default-libmysqlclient-dev libmariadb3 && \
  # Install pipenv
  pip3 --disable-pip-version-check install pipenv && \
  # Create a 'app' user which the application will run as
  groupadd app && \
  useradd -M -d /app -s /bin/false -g app app && \
  # Install non-distro packages
  pipenv install --system && \
  # Make absolutely sure we didn't accidentally bundle a SQLite dev database
  rm -rf /app/db.sqlite3 && \
  # Run any required app commands
  /usr/bin/python3 /app/manage.py compilescss && \
  /usr/bin/python3 /app/manage.py collectstatic --no-input --link && \
  # Create config, downloads and run dirs
  mkdir -p /run/app && \
  mkdir -p /config/media && \
  mkdir -p /downloads/audio && \
  mkdir -p /downloads/video && \
  # Clean up
  rm /app/Pipfile && \
  rm /app/Pipfile.lock && \
  pipenv --clear && \
  pip3 --disable-pip-version-check uninstall -y pipenv wheel virtualenv && \
  apt-get -y autoremove --purge python3-pip python3-dev gcc make default-libmysqlclient-dev && \
  apt-get -y autoremove && \
  apt-get -y autoclean && \
  rm -rf /var/lib/apt/lists/* && \
  rm -rf /var/cache/apt/* && \
  rm -rf /tmp/* && \
  # Pipenv leaves a bunch of stuff in /root, as we're not using it recreate it
  rm -rf /root && \
  mkdir -p /root && \
  chown root:root /root && \
  chmod 0700 /root

# Copy root
COPY config/root /

# Create a healthcheck
HEALTHCHECK --interval=1m --timeout=10s CMD /app/healthcheck.py http://127.0.0.1:8080/healthcheck

# ENVS and ports
ENV PYTHONPATH "/app:${PYTHONPATH}"
EXPOSE 8080

# Volumes
VOLUME ["/config", "/downloads"]

# Entrypoint, start s6 init
ENTRYPOINT ["/init"]
