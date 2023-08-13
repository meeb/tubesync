FROM debian:bookworm-slim

ARG TARGETPLATFORM
ARG S6_VERSION="3.1.2.1"
ARG FFMPEG_DATE="autobuild-2023-08-12-14-12"
ARG FFMPEG_VERSION="111750-g9c694804fd"

ENV DEBIAN_FRONTEND="noninteractive" \
  HOME="/root" \
  LANGUAGE="en_US.UTF-8" \
  LANG="en_US.UTF-8" \
  LC_ALL="en_US.UTF-8" \
  TERM="xterm" \
  S6_CMD_WAIT_FOR_SERVICES_MAXTIME="0"

# Install third party software
RUN export ARCH=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "amd64"  ;; \
  "linux/arm64")   echo "aarch64" ;; \
  *)               echo ""        ;; esac) && \
  export S6_ARCH_EXPECTED_SHA256=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "6019b6b06cfdbb1d1cd572d46b9b158a4904fd19ca59d374de4ddaaa6a3727d5" ;; \
  "linux/arm64")   echo "e73f9a021b64f88278830742149c14ef8a52331102881ba025bf32a66a0e7c78" ;; \
  *)               echo ""        ;; esac) && \
  export S6_DOWNLOAD_ARCH=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-x86_64.tar.xz"   ;; \
  "linux/arm64")   echo "https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}/s6-overlay-aarch64.tar.xz" ;; \
  *)               echo ""        ;; esac) && \
  export FFMPEG_EXPECTED_SHA256=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "df45b74ff59922576226fb15f1875054eed4078115fa0c3bc6b6d96d9bb50cb3" ;; \
  "linux/arm64")   echo "36a8c5f7327bd287c1b4609bb2da4eeb8733b8830aad081911689c6d962032b5" ;; \
  *)               echo ""        ;; esac) && \
  export FFMPEG_DOWNLOAD=$(case ${TARGETPLATFORM:-linux/amd64} in \
  "linux/amd64")   echo "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/${FFMPEG_DATE}/ffmpeg-N-${FFMPEG_VERSION}-linux64-gpl.tar.xz"   ;; \
  "linux/arm64")   echo "https://github.com/yt-dlp/FFmpeg-Builds/releases/download/${FFMPEG_DATE}/ffmpeg-N-${FFMPEG_VERSION}-linuxarm64-gpl.tar.xz" ;; \
  *)               echo ""        ;; esac) && \
  export S6_NOARCH_EXPECTED_SHA256="cee89d3eeabdfe15239b2c5c3581d9352d2197d4fd23bba3f1e64bf916ccf496" && \
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
  apt-get -y autoremove --purge curl binutils xz-utils

# Copy app
COPY tubesync /app
COPY tubesync/tubesync/local_settings.py.container /app/tubesync/local_settings.py

# Copy over pip.conf to use piwheels
COPY pip.conf /etc/pip.conf

# Add Pipfile
COPY Pipfile /app/Pipfile

# Switch workdir to the the app
WORKDIR /app

# Set up the app
RUN set -x && \
  apt-get update && \
  # Install required distro packages
  apt-get -y install nginx-light && \
  apt-get -y --no-install-recommends install \
  python3 \
  python3-dev \
  python3-pip \
  python3-wheel \
  pipenv \
  gcc \
  g++ \
  make \
  pkgconf \
  default-libmysqlclient-dev \
  libmariadb3 \
  postgresql-common \
  libpq-dev \
  libpq5 \
  libjpeg62-turbo \
  libwebp7 \
  libjpeg-dev \
  zlib1g-dev \
  libwebp-dev \
  redis-server && \
  # Create a 'app' user which the application will run as
  groupadd app && \
  useradd -M -d /app -s /bin/false -g app app && \
  # Install non-distro packages
  PIPENV_VERBOSITY=64 pipenv install --system --skip-lock && \
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
  pipenv --clear && \
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
  chmod 0755 /root

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
