ARG FFMPEG_DATE="2025-01-10-19-43"
ARG FFMPEG_VERSION="N-118280-g5cd49e1bfd"

ARG S6_VERSION="3.2.0.2"

ARG SHA256_S6_AMD64="59289456ab1761e277bd456a95e737c06b03ede99158beb24f12b165a904f478"
ARG SHA256_S6_ARM64="8b22a2eaca4bf0b27a43d36e65c89d2701738f628d1abd0cea5569619f66f785"
ARG SHA256_S6_NOARCH="6dbcde158a3e78b9bb141d7bcb5ccb421e563523babbe2c64470e76f4fd02dae"

ARG ALPINE_VERSION="latest"
ARG FFMPEG_PREFIX_FILE="ffmpeg-${FFMPEG_VERSION%%-*}"
ARG FFMPEG_SUFFIX_FILE=".tar.xz"

FROM alpine:${ALPINE_VERSION} AS ffmpeg-download
ARG FFMPEG_DATE
ARG FFMPEG_VERSION
ARG FFMPEG_PREFIX_FILE
ARG FFMPEG_SUFFIX_FILE
ARG SHA256_FFMPEG_AMD64
ARG SHA256_FFMPEG_ARM64
ARG CHECKSUM_ALGORITHM="sha256"
ARG FFMPEG_CHECKSUM_AMD64="${SHA256_FFMPEG_AMD64}"
ARG FFMPEG_CHECKSUM_ARM64="${SHA256_FFMPEG_ARM64}"

ARG FFMPEG_FILE_SUMS="checksums.${CHECKSUM_ALGORITHM}"
ARG FFMPEG_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/download/autobuild-${FFMPEG_DATE}"

ARG DESTDIR="/downloaded"
ARG TARGETARCH
ADD "${FFMPEG_URL}/${FFMPEG_FILE_SUMS}" "${DESTDIR}/"
RUN <<EOF
    set -eu
    apk --no-cache --no-progress add cmd:aria2c cmd:awk

    aria2c_options() {
        algorithm="${CHECKSUM_ALGORITHM%[0-9]??}"
        bytes="${CHECKSUM_ALGORITHM#${algorithm}}"
        hash="$( awk -v fn="${1##*/}" '$0 ~ fn"$" { print $1; exit; }' "${DESTDIR}/${FFMPEG_FILE_SUMS}" )"

        printf -- '\t%s\n' \
          'allow-overwrite=true' \
          'always-resume=false' \
          'check-integrity=true' \
          "checksum=${algorithm}-${bytes}=${hash}" \
          'max-connection-per-server=2' \

        # the blank line above was intentional
        printf -- '\n'
    }

    # files to retrieve are in the sums file
    for url in $(awk '
      $2 ~ /^[*]?'"${FFMPEG_PREFIX_FILE}"'/ && /-linux/ { $1=""; print; }
      ' "${DESTDIR}/${FFMPEG_FILE_SUMS}")
    do
        url="${FFMPEG_URL}/${url# }"
        printf -- '%s\n' "${url}"
        aria2c_options "${url}"
        printf -- '\n'
    done > /tmp/downloads
    unset -v url

    aria2c --no-conf=true \
      --dir /downloaded \
      --lowest-speed-limit='16K' \
      --show-console-readout=false \
      --summary-interval=0 \
      --input-file /tmp/downloads
EOF

RUN <<EOF
    set -eu
    apk --no-cache --no-progress add cmd:awk "cmd:${CHECKSUM_ALGORITHM}sum"

    decide_arch() {
        case "${TARGETARCH}" in
            (amd64) printf -- 'linux64' ;;
            (arm64) printf -- 'linuxarm64' ;;
        esac
    }
    
    decide_expected() {
        case "${TARGETARCH}" in \
            (amd64) printf -- '%s' "${FFMPEG_CHECKSUM_AMD64}" ;; \
            (arm64) printf -- '%s' "${FFMPEG_CHECKSUM_ARM64}" ;; \
        esac
    }

    FFMPEG_ARCH="$(decide_arch)"
    FFMPEG_HASH="$(decide_expected)"

    cd "${DESTDIR}"
    if [ -n "${FFMPEG_HASH}" ]
    then
        printf -- '%s *%s\n' "${FFMPEG_HASH}" "${FFMPEG_PREFIX_FILE}"*-"${FFMPEG_ARCH}"-*"${FFMPEG_SUFFIX_FILE}" >> /tmp/SUMS
        "${CHECKSUM_ALGORITHM}sum" --check --strict /tmp/SUMS || exit
    fi
    "${CHECKSUM_ALGORITHM}sum" --check --strict --ignore-missing "${DESTDIR}/${FFMPEG_FILE_SUMS}"

    mkdir -v -p "/verified/${TARGETARCH}"
    ln -v "${FFMPEG_PREFIX_FILE}"*-"${FFMPEG_ARCH}"-*"${FFMPEG_SUFFIX_FILE}" "/verified/${TARGETARCH}/"
EOF

FROM alpine:${ALPINE_VERSION} AS ffmpeg-extracted
COPY --from=ffmpeg-download /verified /verified

ARG FFMPEG_PREFIX_FILE
ARG FFMPEG_SUFFIX_FILE
ARG TARGETARCH
RUN <<EOF
    set -eu
    apk --no-cache --no-progress add cmd:tar cmd:xz
    
    mkdir -v /extracted
    cd /extracted
    tar -xp \
      --strip-components=2 \
      --no-anchored \
      --no-same-owner \
      -f "/verified/${TARGETARCH}"/"${FFMPEG_PREFIX_FILE}"*"${FFMPEG_SUFFIX_FILE}" \
      'ffmpeg' 'ffprobe'

    ls -AlR /extracted
EOF

FROM scratch AS ffmpeg
COPY --from=ffmpeg-extracted /extracted /usr/local/bin

FROM scratch AS s6-overlay-download
ARG S6_VERSION
ARG SHA256_S6_AMD64
ARG SHA256_S6_ARM64
ARG SHA256_S6_NOARCH

ARG DESTDIR="/downloaded"
ARG CHECKSUM_ALGORITHM="sha256"

ARG S6_CHECKSUM_AMD64="${CHECKSUM_ALGORITHM}:${SHA256_S6_AMD64}"
ARG S6_CHECKSUM_ARM64="${CHECKSUM_ALGORITHM}:${SHA256_S6_ARM64}"
ARG S6_CHECKSUM_NOARCH="${CHECKSUM_ALGORITHM}:${SHA256_S6_NOARCH}"

ARG S6_OVERLAY_URL="https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}"
ARG S6_PREFIX_FILE="s6-overlay-"
ARG S6_SUFFIX_FILE=".tar.xz"

ARG S6_FILE_AMD64="${S6_PREFIX_FILE}x86_64${S6_SUFFIX_FILE}"
ARG S6_FILE_ARM64="${S6_PREFIX_FILE}aarch64${S6_SUFFIX_FILE}"
ARG S6_FILE_NOARCH="${S6_PREFIX_FILE}noarch${S6_SUFFIX_FILE}"

ADD --link "${S6_OVERLAY_URL}/${S6_FILE_AMD64}.${CHECKSUM_ALGORITHM}" "${DESTDIR}/"
ADD --link "${S6_OVERLAY_URL}/${S6_FILE_ARM64}.${CHECKSUM_ALGORITHM}" "${DESTDIR}/"
ADD --link "${S6_OVERLAY_URL}/${S6_FILE_NOARCH}.${CHECKSUM_ALGORITHM}" "${DESTDIR}/"

ADD --link --checksum="${S6_CHECKSUM_AMD64}" "${S6_OVERLAY_URL}/${S6_FILE_AMD64}" "${DESTDIR}/"
ADD --link --checksum="${S6_CHECKSUM_ARM64}" "${S6_OVERLAY_URL}/${S6_FILE_ARM64}" "${DESTDIR}/"
ADD --link --checksum="${S6_CHECKSUM_NOARCH}" "${S6_OVERLAY_URL}/${S6_FILE_NOARCH}" "${DESTDIR}/"

FROM alpine:${ALPINE_VERSION} AS s6-overlay-extracted
COPY --from=s6-overlay-download /downloaded /downloaded

ARG TARGETARCH

RUN <<EOF
    set -eu

    decide_arch() {
      local arg1
      arg1="${1:-$(uname -m)}"

      case "${arg1}" in
        (amd64) printf -- 'x86_64' ;;
        (arm64) printf -- 'aarch64' ;;
        (armv7l) printf -- 'arm' ;;
        (*) printf -- '%s' "${arg1}" ;;
      esac
      unset -v arg1
    }

    mkdir -v /verified
    cd /downloaded
    for f in *.sha256
    do
      sha256sum -c < "${f}" || exit
      ln -v "${f%.sha256}" /verified/ || exit
    done
    unset -v f

    S6_ARCH="$(decide_arch "${TARGETARCH}")"
    set -x
    mkdir -v /s6-overlay-rootfs
    cd /s6-overlay-rootfs
    for f in /verified/*.tar*
    do
      case "${f}" in
        (*-noarch.tar*|*-"${S6_ARCH}".tar*)
          tar -xpf "${f}" || exit ;;
      esac
    done
    set +x
    unset -v f
EOF

FROM scratch AS s6-overlay
COPY --from=s6-overlay-extracted /s6-overlay-rootfs /

FROM debian:bookworm-slim

ARG TARGETARCH
ARG TARGETPLATFORM

ARG S6_VERSION

ARG FFMPEG_DATE
ARG FFMPEG_VERSION

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
COPY --link --from=s6-overlay / /
COPY --link --from=ffmpeg /usr/local/bin/ /usr/local/bin/

# Reminder: the SHELL handles all variables
RUN set -x && \
  apt-get update && \
  apt-get -y --no-install-recommends install locales && \
  printf -- "en_US.UTF-8 UTF-8\n" > /etc/locale.gen && \
  locale-gen en_US.UTF-8 && \
  # Install required distro packages
  apt-get -y --no-install-recommends install curl ca-certificates file binutils xz-utils && \
  # Installed s6 (using COPY earlier)
  file -L /command/s6-overlay-suexec && \
  # Installed ffmpeg (using COPY earlier)
  /usr/local/bin/ffmpeg -version && \
  file /usr/local/bin/ff* && \
  # Clean up
  apt-get -y autoremove --purge file binutils xz-utils && \
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
  curl \
  less \
  && apt-get -y autoclean && \
  rm -rf /var/lib/apt/lists/* && \
  rm -rf /var/cache/apt/* && \
  rm -rf /tmp/*

# Copy over pip.conf to use piwheels
COPY pip.conf /etc/pip.conf

# Do not include compiled byte-code
ENV PIP_NO_COMPILE=1 \
  PIP_NO_CACHE_DIR=1 \
  PIP_ROOT_USER_ACTION='ignore'

# Switch workdir to the the app
WORKDIR /app

# Set up the app
RUN --mount=type=bind,source=Pipfile,target=/app/Pipfile \ 
  set -x && \
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
  /usr/bin/python3 -B /app/manage.py compilescss && \
  /usr/bin/python3 -B /app/manage.py collectstatic --no-input --link && \
  # Create config, downloads and run dirs
  mkdir -v -p /run/app && \
  mkdir -v -p /config/media && \
  mkdir -v -p /config/cache/pycache && \
  mkdir -v -p /downloads/audio && \
  mkdir -v -p /downloads/video


# Append software versions
RUN set -x && \
  ffmpeg_version=$(/usr/local/bin/ffmpeg -version | awk -v 'ev=31' '1 == NR && "ffmpeg" == $1 { print $3; ev=0; } END { exit ev; }') && \
  test -n "${ffmpeg_version}" && \
  printf -- "ffmpeg_version = '%s'\n" "${ffmpeg_version}" >> /app/common/third_party_versions.py

# Copy root
COPY config/root /

# Create a healthcheck
HEALTHCHECK --interval=1m --timeout=10s CMD /app/healthcheck.py http://127.0.0.1:8080/healthcheck

# ENVS and ports
ENV PYTHONPATH="/app" PYTHONPYCACHEPREFIX="/config/cache/pycache"
EXPOSE 4848

# Volumes
VOLUME ["/config", "/downloads"]

# Entrypoint, start s6 init
ENTRYPOINT ["/init"]
