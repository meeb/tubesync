FROM debian:bookworm-slim

ARG TARGETARCH
ARG TARGETPLATFORM

ARG S6_VERSION="3.2.0.0"
ARG FFMPEG_DATE="autobuild-2024-10-30-14-17"
ARG FFMPEG_VERSION="117674-g44a0a0c050"

ENV S6_VERSION="${S6_VERSION}" \
  FFMPEG_DATE="${FFMPEG_DATE}" \
  FFMPEG_VERSION="${FFMPEG_VERSION}"

ENV DEBIAN_FRONTEND="noninteractive" \
  HOME="/root" \
  LANGUAGE="en_US.UTF-8" \
  LANG="en_US.UTF-8" \
  LC_ALL="en_US.UTF-8" \
  TERM="xterm" \
  S6_CMD_WAIT_FOR_SERVICES_MAXTIME="0"

# Install third party software
RUN export ARCH="$(case "${TARGETARCH:-amd64}" in \
  arm64) echo 'aarch64' ;; \
  *)     echo "${TARGETARCH:-amd64}" ;; esac)" && \
  export S6_ARCH_EXPECTED_SHA256=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "ad982a801bd72757c7b1b53539a146cf715e640b4d8f0a6a671a3d1b560fe1e2" ;; \
  "linux/arm64")   echo "868973e98210257bba725ff5b17aa092008c9a8e5174499e38ba611a8fc7e473" ;; \
  *)               echo ""        ;; esac) && \
  export S6_DOWNLOAD_ARCH=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-x86_64.tar.xz"   ;; \
  "linux/arm64")   echo "https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-aarch64.tar.xz" ;; \
  *)               echo ""        ;; esac) && \
  export FFMPEG_EXPECTED_SHA256=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "08f889687ca9706171c2b534ff241e0e1fda082f27f2ddd9fedf14a8e7b5f1aa" ;; \
  "linux/arm64")   echo "a2ea26c54b1c79b63a6b51b5c228b6a350fe790c4c75e5d0889636b37e2e694b" ;; \
  *)               echo ""        ;; esac) && \
  export FFMPEG_DOWNLOAD=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/${FFMPEG_DATE}/ffmpeg-N-${FFMPEG_VERSION}-linux64-gpl.tar.xz"   ;; \
  "linux/arm64")   echo "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/${FFMPEG_DATE}/ffmpeg-N-${FFMPEG_VERSION}-linuxarm64-gpl.tar.xz" ;; \
  *)               echo ""        ;; esac) && \
  export S6_NOARCH_EXPECTED_SHA256="4b0c0907e6762814c31850e0e6c6762c385571d4656eb8725852b0b1586713b6" && \
  export S6_DOWNLOAD_NOARCH="https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-noarch.tar.xz" && \
  echo "Building for arch: ${ARCH}|${ARCH44}, downloading S6 from: ${S6_DOWNLOAD}}, expecting S6 SHA256: ${S6_EXPECTED_SHA256}" && \
  set -x && \
  apt-get update && \
  apt-get -y --no-install-recommends install locales && \
  echo "en_US.UTF-8 UTF-8" > /etc/locale.gen && \
  locale-gen en_US.UTF-8 && \
  # Install required distro packages
  apt-get -y --no-install-recommends install curl ca-certificates binutils xz-utils && \
  # Install s6
  curl -L ${S6_DOWNLOAD_NOARCH} --output /tmp/s6-overlay-noarch.tar.xz && \
  echo "${S6_NOARCH_EXPECTED_SHA256}  /tmp/s6-overlay-noarch.tar.xz" | sha256sum -c - && \
  tar -C / -Jxpf /tmp/s6-overlay-noarch.tar.xz && \
  curl -L ${S6_DOWNLOAD_ARCH} --output /tmp/s6-overlay-${ARCH}.tar.xz && \
  echo "${S6_ARCH_EXPECTED_SHA256}  /tmp/s6-overlay-${ARCH}.tar.xz" | sha256sum -c - && \
  tar -C / -Jxpf /tmp/s6-overlay-${ARCH}.tar.xz && \
  # Install ffmpeg
  echo "Building for arch: ${ARCH}|${ARCH44}, downloading FFMPEG from: ${FFMPEG_DOWNLOAD}, expecting FFMPEG SHA256: ${FFMPEG_EXPECTED_SHA256}" && \
  curl -L ${FFMPEG_DOWNLOAD} --output /tmp/ffmpeg-${ARCH}.tar.xz && \
  sha256sum /tmp/ffmpeg-${ARCH}.tar.xz && \
  echo "${FFMPEG_EXPECTED_SHA256}  /tmp/ffmpeg-${ARCH}.tar.xz" | sha256sum -c - && \
  tar -xf /tmp/ffmpeg-${ARCH}.tar.xz --strip-components=2 --no-anchored -C /usr/local/bin/ "ffmpeg" && \
  tar -xf /tmp/ffmpeg-${ARCH}.tar.xz --strip-components=2 --no-anchored -C /usr/local/bin/ "ffprobe" && \
  # Clean up
  rm -rf /tmp/s6-overlay-${ARCH}.tar.gz && \
  rm -rf /tmp/ffmpeg-${ARCH}.tar.xz && \
  apt-get -y autoremove --purge curl binutils xz-utils && \
  rm -rf /var/lib/apt/lists/* && \
  rm -rf /var/cache/apt/* && \
  rm -rf /tmp/*

# Install dependencies we keep
RUN set -x && \
  apt-get update && \
  # Install required distro packages
  apt-get -y --no-install-recommends install \
  libjpeg62-turbo \
  libmariadb3 \
  libpq5 \
  libwebp7 \
  nginx-light \
  pipenv \
  pkgconf \
  python3 \
  python3-wheel \
  redis-server \
  && apt-get -y autoclean && \
  rm -rf /var/lib/apt/lists/* && \
  rm -rf /var/cache/apt/* && \
  rm -rf /tmp/*

# Copy over pip.conf to use piwheels
COPY pip.conf /etc/pip.conf

# Add Pipfile
COPY Pipfile /app/Pipfile

# Switch workdir to the the app
WORKDIR /app

# Set up the app
RUN set -x && \
  apt-get update && \
  # Install required build packages
  apt-get -y --no-install-recommends install \
  default-libmysqlclient-dev \
  g++ \
  gcc \
  libjpeg-dev \
  libpq-dev \
  libwebp-dev \
  make \
  postgresql-common \
  python3-dev \
  python3-pip \
  zlib1g-dev \
  && \
  # Create a 'app' user which the application will run as
  groupadd app && \
  useradd -M -d /app -s /bin/false -g app app && \
  # Install non-distro packages
  PIPENV_VERBOSITY=64 pipenv install --system --skip-lock && \
  # Clean up
  rm /app/Pipfile && \
  pipenv --clear && \
  apt-get -y autoremove --purge \
  default-libmysqlclient-dev \
  g++ \
  gcc \
  libjpeg-dev \
  libpq-dev \
  libwebp-dev \
  make \
  postgresql-common \
  python3-dev \
  python3-pip \
  zlib1g-dev \
  && \
  apt-get -y autoremove && \
  apt-get -y autoclean && \
  rm -rf /var/lib/apt/lists/* && \
  rm -rf /var/cache/apt/* && \
  rm -rf /tmp/* && \
  # Pipenv leaves a bunch of stuff in /root, as we're not using it recreate it
  rm -rf /root && \
  mkdir -p /root && \
  chown root:root /root && \
  chmod 0755 /root


# Copy app
COPY tubesync /app
COPY tubesync/tubesync/local_settings.py.container /app/tubesync/local_settings.py

# Build app
RUN set -x && \
  # Make absolutely sure we didn't accidentally bundle a SQLite dev database
  rm -rf /app/db.sqlite3 && \
  # Run any required app commands
  /usr/bin/python3 /app/manage.py compilescss && \
  /usr/bin/python3 /app/manage.py collectstatic --no-input --link && \
  # Create config, downloads and run dirs
  mkdir -p /run/app && \
  mkdir -p /config/media && \
  mkdir -p /downloads/audio && \
  mkdir -p /downloads/video


# Append software versions
RUN set -x && \
  FFMPEG_VERSION=$(/usr/local/bin/ffmpeg -version | head -n 1 | awk '{ print $3 }') && \
  echo "ffmpeg_version = '${FFMPEG_VERSION}'" >> /app/common/third_party_versions.py

# Copy root
COPY config/root /

# Create a healthcheck
HEALTHCHECK --interval=1m --timeout=10s CMD /app/healthcheck.py http://127.0.0.1:8080/healthcheck

# ENVS and ports
ENV PYTHONPATH="/app"
EXPOSE 4848

# Volumes
VOLUME ["/config", "/downloads"]

# Entrypoint, start s6 init
ENTRYPOINT ["/init"]
