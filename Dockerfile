FROM debian:bookworm-slim

ARG TARGETARCH
ARG TARGETPLATFORM

ARG S6_VERSION="3.2.0.0"
ARG SHA256_S6_AMD64="ad982a801bd72757c7b1b53539a146cf715e640b4d8f0a6a671a3d1b560fe1e2"
ARG SHA256_S6_ARM64="868973e98210257bba725ff5b17aa092008c9a8e5174499e38ba611a8fc7e473"
ARG SHA256_S6_NOARCH="4b0c0907e6762814c31850e0e6c6762c385571d4656eb8725852b0b1586713b6"

ARG FFMPEG_DATE="autobuild-2024-11-22-14-18"
ARG FFMPEG_VERSION="117857-g2d077f9acd"
ARG SHA256_FFMPEG_AMD64="427ff38cf1e28521aac4fa7931444f6f2ff6f097f2d4a315c6f92ef1d7f90db8"
ARG SHA256_FFMPEG_ARM64="f7ed3a50b651447477aa2637bf8da6010d8f27f8804a5d0e77b00a1d3725b27a"

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
# Reminder: the SHELL handles all variables
RUN decide_arch() { \
      case "${TARGETARCH:=amd64}" in \
        (arm64) printf -- 'aarch64' ;; \
        (*) printf -- '%s' "${TARGETARCH}" ;; \
      esac ; \
    } && \
    decide_expected() { \
      case "${1}" in \
        (ffmpeg) case "${2}" in \
            (amd64) printf -- '%s' "${SHA256_FFMPEG_AMD64}" ;; \
            (arm64) printf -- '%s' "${SHA256_FFMPEG_ARM64}" ;; \
          esac ;; \
        (s6) case "${2}" in \
            (amd64) printf -- '%s' "${SHA256_S6_AMD64}" ;; \
            (arm64) printf -- '%s' "${SHA256_S6_ARM64}" ;; \
            (noarch) printf -- '%s' "${SHA256_S6_NOARCH}" ;; \
          esac ;; \
      esac ; \
    } && \
    decide_url() { \
      case "${1}" in \
        (ffmpeg) printf -- \
          'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/%s/ffmpeg-N-%s-linux%s-gpl.tar.xz' \
          "${FFMPEG_DATE}" \
          "${FFMPEG_VERSION}" \
          "$(case "${2}" in \
            (amd64) printf -- '64' ;; \
            (*) printf -- '%s' "${2}" ;; \
          esac)" ;; \
        (s6) printf -- \
          'https://github.com/just-containers/s6-overlay/releases/download/v%s/s6-overlay-%s.tar.xz' \
          "${S6_VERSION}" \
          "$(case "${2}" in \
            (amd64) printf -- 'x86_64' ;; \
            (arm64) printf -- 'aarch64' ;; \
            (*) printf -- '%s' "${2}" ;; \
          esac)" ;; \
      esac ; \
    } && \
    verify_download() { \
      while [ $# -ge 2 ] ; do \
        sha256sum "${2}" ; \
        printf -- '%s  %s\n' "${1}" "${2}" | sha256sum -c || return ; \
        shift ; shift ; \
      done ; \
    } && \
    download_expected_file() { \
      local arg1 expected file url ; \
      arg1="$(printf -- '%s\n' "${1}" | awk '{print toupper($0);}')" ; \
      expected="$(decide_expected "${1}" "${2}")" ; \
      file="${3}" ; \
      url="$(decide_url "${1}" "${2}")" ; \
      printf -- '%s\n' \
        "Building for arch: ${2}|${ARCH}, downloading ${arg1} from: ${url}, expecting ${arg1} SHA256: ${expected}" && \
      curl -sSL --output "${file}" "${url}" && \
      verify_download "${expected}" "${file}" ; \
    } && \
  export ARCH="$(decide_arch)" && \
  set -x && \
  apt-get update && \
  apt-get -y --no-install-recommends install locales && \
  printf -- "en_US.UTF-8 UTF-8\n" > /etc/locale.gen && \
  locale-gen en_US.UTF-8 && \
  # Install required distro packages
  apt-get -y --no-install-recommends install curl ca-certificates binutils xz-utils && \
  # Install s6
  _file="/tmp/s6-overlay-noarch.tar.xz" && \
  download_expected_file s6 noarch "${_file}" && \
  tar -C / -xpf "${_file}" && rm -f "${_file}" && \
  _file="/tmp/s6-overlay-${ARCH}.tar.xz" && \
  download_expected_file s6 "${TARGETARCH}" "${_file}" && \
  tar -C / -xpf "${_file}" && rm -f "${_file}" && \
  # Install ffmpeg
  _file="/tmp/ffmpeg-${ARCH}.tar.xz" && \
  download_expected_file ffmpeg "${TARGETARCH}" "${_file}" && \
  tar -xvvpf "${_file}" --strip-components=2 --no-anchored -C /usr/local/bin/ "ffmpeg" "ffprobe" && rm -f "${_file}" && \
  # Clean up
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
  cp -at /tmp/ "${HOME}" && \
  PIPENV_VERBOSITY=64 HOME="/tmp/${HOME#/}" pipenv install --system --skip-lock && \
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
  rm -rf /tmp/*


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
  mkdir -v -p /run/app && \
  mkdir -v -p /config/media && \
  mkdir -v -p /downloads/audio && \
  mkdir -v -p /downloads/video


# Append software versions
RUN set -x && \
  /usr/local/bin/ffmpeg -version && \
  FFMPEG_VERSION=$(set -o pipefail ; /usr/local/bin/ffmpeg -version | head -n 1 | awk '{ print $3 }' || exit) && \
  printf -- "ffmpeg_version = '%s'\n" "${FFMPEG_VERSION}" >> /app/common/third_party_versions.py

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
