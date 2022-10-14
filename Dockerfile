FROM debian:bullseye-slim

ARG TARGETPLATFORM
ARG S6_VERSION="2.2.0.3"

ENV DEBIAN_FRONTEND="noninteractive" \
  HOME="/root" \
  LANGUAGE="en_US.UTF-8" \
  LANG="en_US.UTF-8" \
  LC_ALL="en_US.UTF-8" \
  TERM="xterm"

# Install third party software
RUN export ARCH=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "amd64"  ;; \
  "linux/arm64")   echo "aarch64" ;; \
  *)               echo ""        ;; esac) && \
  export S6_EXPECTED_SHA256=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "a7076cf205b331e9f8479bbb09d9df77dbb5cd8f7d12e9b74920902e0c16dd98"  ;; \
  "linux/arm64")   echo "84f585a100b610124bb80e441ef2dc2d68ac2c345fd393d75a6293e0951ccfc5" ;; \
  *)               echo ""        ;; esac) && \
  export S6_DOWNLOAD=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-amd64.tar.gz"  ;; \
  "linux/arm64")   echo "https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-aarch64.tar.gz" ;; \
  *)               echo ""        ;; esac) && \
  export FFMPEG_EXPECTED_SHA256=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "b81c8b5ae1eb42db1001689682c52d2c02fbecdd2683598412678d3d3918bbd0"  ;; \
  "linux/arm64")   echo "627b1f31c5f5feb76ce78b39afd233f5faf615bc43b52a783b3bd17586c69ec0" ;; \
  *)               echo ""        ;; esac) && \
  export FFMPEG_DOWNLOAD=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linux64-gpl.tar.xz"  ;; \
  "linux/arm64")   echo "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-linuxarm64-gpl.tar.xz" ;; \
  *)               echo ""        ;; esac) && \
  echo "Building for arch: ${ARCH}|${ARCH44}, downloading S6 from: ${S6_DOWNLOAD}}, expecting S6 SHA256: ${S6_EXPECTED_SHA256}" && \
  set -x && \
  apt-get update && \
  apt-get -y --no-install-recommends install locales && \
  echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && \
  locale-gen en_US.UTF-8 && \
  # Install required distro packages
  apt-get -y --no-install-recommends install curl ca-certificates binutils xz-utils && \
  # Install s6
  curl -L ${S6_DOWNLOAD} --output /tmp/s6-overlay-${ARCH}.tar.gz && \
  sha256sum /tmp/s6-overlay-${ARCH}.tar.gz && \
  echo "${S6_EXPECTED_SHA256} /tmp/s6-overlay-${ARCH}.tar.gz" | sha256sum -c - && \
  tar xzf /tmp/s6-overlay-${ARCH}.tar.gz -C / && \
  echo "Building for arch: ${ARCH}|${ARCH44}, downloading FFMPEG from: ${FFMPEG_DOWNLOAD}, expecting FFMPEG SHA256: ${FFMPEG_EXPECTED_SHA256}" && \
  curl -L ${FFMPEG_DOWNLOAD} --output /tmp/ffmpeg-${ARCH}.tar.xz && \
  sha256sum /tmp/ffmpeg-${ARCH}.tar.xz && \
  echo "${FFMPEG_EXPECTED_SHA256}  /tmp/ffmpeg-${ARCH}.tar.xz" | sha256sum -c - && \
  tar -xf /tmp/ffmpeg-${ARCH}.tar.xz --strip-components=2 --no-anchored -C /usr/local/bin/ "ffmpeg" && \
  tar -xf /tmp/ffmpeg-${ARCH}.tar.xz --strip-components=2 --no-anchored -C /usr/local/bin/ "ffprobe" && \
  # Clean up
  rm -rf /tmp/s6-overlay-${ARCH}.tar.gz && \
  rm -rf /tmp/ffmpeg-${ARCH}.tar.xz && \
  apt-get -y autoremove --purge curl binutils xz-utils

# Copy app
COPY tubesync /app
COPY tubesync/tubesync/local_settings.py.container /app/tubesync/local_settings.py

# Copy over pip.conf to use piwheels
COPY pip.conf /etc/pip.conf

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
  apt-get -y --no-install-recommends install \
  python3 \
  python3-setuptools \
  python3-pip \
  python3-dev \
  gcc \
  g++ \
  make \
  default-libmysqlclient-dev \
  libmariadb3 \
  postgresql-common \
  libpq-dev \
  libpq5 \
  libjpeg62-turbo \
  libwebp6 \
  libjpeg-dev \
  zlib1g-dev \
  libwebp-dev \
  redis-server && \
  # Install pipenv
  pip3 --disable-pip-version-check install wheel pipenv && \
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
  apt-get -y autoremove --purge \
  python3-pip \
  python3-dev \
  gcc \
  g++ \
  make \
  default-libmysqlclient-dev \
  postgresql-common \
  libpq-dev \
  libjpeg-dev \
  zlib1g-dev \
  libwebp-dev && \
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

# Append software versions
RUN set -x && \
  FFMPEG_VERSION=$(/usr/local/bin/ffmpeg -version | head -n 1 | awk '{ print $3 }') && \
  echo "ffmpeg_version = '${FFMPEG_VERSION}'" >> /app/common/third_party_versions.py

# Copy root
COPY config/root /

# Create a healthcheck
HEALTHCHECK --interval=1m --timeout=10s CMD /app/healthcheck.py http://127.0.0.1:8080/healthcheck

# ENVS and ports
ENV PYTHONPATH "/app:${PYTHONPATH}"
EXPOSE 4848

# Volumes
VOLUME ["/config", "/downloads"]

# Entrypoint, start s6 init
ENTRYPOINT ["/init"]
