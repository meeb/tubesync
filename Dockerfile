ARG FFMPEG_DATE="2025-01-10-19-43"
ARG FFMPEG_VERSION="N-118280-g5cd49e1bfd"
ARG SHA256_FFMPEG_AMD64="40842d6783e942904b0e8b5627e83e5d668c48e91396fe3629f440c75213027b"
ARG SHA256_FFMPEG_ARM64="e022ee91d1146dca07fdc0bda9f35141e72d2f186ac89714ca63ff501b606b9f"

ARG S6_VERSION="3.2.0.2"

ARG SHA256_S6_AMD64="59289456ab1761e277bd456a95e737c06b03ede99158beb24f12b165a904f478"
ARG SHA256_S6_ARM64="8b22a2eaca4bf0b27a43d36e65c89d2701738f628d1abd0cea5569619f66f785"
ARG SHA256_S6_NOARCH="6dbcde158a3e78b9bb141d7bcb5ccb421e563523babbe2c64470e76f4fd02dae"

ARG ALPINE_VERSION="latest"

FROM alpine:${ALPINE_VERSION} AS ffmpeg-extracted
ARG FFMPEG_DATE
ARG FFMPEG_VERSION
ARG SHA256_FFMPEG_AMD64
ARG SHA256_FFMPEG_ARM64

ARG FFMPEG_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/download/autobuild-${FFMPEG_DATE}"
ARG FFMPEG_PREFIX_FILE="ffmpeg-"
ARG FFMPEG_SUFFIX_FILE=".tar.xz"

ARG FFMPEG_FILE_SUMS="checksums.sha256"

ADD "${FFMPEG_URL}/${FFMPEG_FILE_SUMS}" /downloaded/
RUN <<EOF
    set -eux
    apk --no-cache --no-progress add cmd:aria2c cmd:awk cmd:sha256sum

    aria2c_options() {
        hash="$( awk -v fn="${1##*/}" '$0 ~ fn"$" { print $1; exit; }' "/downloaded/${FFMPEG_FILE_SUMS}" )"
        printf -- '\t%s\n' \
        "checksum=sha-256=${hash}" \

        # the blank line above was intentional
        printf -- '\n'
    }

    # files to retrieve are in the sums file
    for url in $(awk '
      $2 ~ /^[*]?'"${FFMPEG_PREFIX_FILE}"'/ && /-linux/ { $1=""; print; }
      ' "/downloaded/${FFMPEG_FILE_SUMS}")
    do
        url="${FFMPEG_URL}/${url# }"
        printf -- '%s\n' "${url}"
        aria2c_options "${url}"
        printf -- '\n'
    done > /tmp/downloads
    unset -v url
    aria2c --no-conf=true \
      --dir /downloaded \
      --check-integrity=true \
      --always-resume=false \
      --allow-overwrite=true \
      --max-connection-per-server=4 \
      --lowest-speed-limit='16K' \
      --summary-interval=0 \
      --input-file /tmp/downloads

      ls -alR /downloaded
EOF

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
          tar -xvvpf "${f}" || exit ;;
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
ARG SHA256_FFMPEG_AMD64
ARG SHA256_FFMPEG_ARM64

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
COPY --from=ffmpeg-extracted /downloaded /tmp/

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
      esac ; \
    } && \
    decide_url() { \
      case "${1}" in \
        (ffmpeg) printf -- \
          'https://github.com/yt-dlp/FFmpeg-Builds/releases/download/%s/ffmpeg-%s-linux%s-gpl%s.tar.xz' \
          "autobuild-${FFMPEG_DATE}" \
          "${FFMPEG_VERSION}" \
          "$(case "${2}" in \
            (amd64) printf -- '64' ;; \
            (*) printf -- '%s' "${2}" ;; \
          esac)" \
          "$(case "${FFMPEG_VERSION%%-*}" in \
            (n*) printf -- '-%s\n' "${FFMPEG_VERSION#n}" | cut -d '-' -f 1,2 ;; \
            (*) printf -- '' ;; \
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
      rm -rf "${file}" && \
      { \
        cp -v -l /tmp/downloaded/${url##*/}" "${file}" || \
        curl --disable --output "${file}" --clobber --location --no-progress-meter --url "${url}" ; \
      } && \
      verify_download "${expected}" "${file}" ; \
    } && \
  export ARCH="$(decide_arch)" && \
  set -x && \
  apt-get update && \
  apt-get -y --no-install-recommends install locales && \
  printf -- "en_US.UTF-8 UTF-8\n" > /etc/locale.gen && \
  locale-gen en_US.UTF-8 && \
  # Install required distro packages
  apt-get -y --no-install-recommends install curl ca-certificates file binutils xz-utils && \
  # Installed s6 (using COPY earlier)
  file -L /command/s6-overlay-suexec && \
  # Install ffmpeg
  _file="/tmp/ffmpeg-${ARCH}.tar.xz" && \
  download_expected_file ffmpeg "${TARGETARCH}" "${_file}" && \
  tar -xvvpf "${_file}" --strip-components=2 --no-anchored -C /usr/local/bin/ "ffmpeg" "ffprobe" && rm -f "${_file}" && \
  file /usr/local/bin/ff* && \
  # Clean up
  apt-get -y autoremove --purge curl file binutils xz-utils && \
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
  /usr/local/bin/ffmpeg -version && \
  FFMPEG_VERSION=$(/usr/local/bin/ffmpeg -version | awk -v 'ev=31' '1 == NR && "ffmpeg" == $1 { print $3; ev=0; } END { exit ev; }') && \
  test -n "${FFMPEG_VERSION}" && \
  printf -- "ffmpeg_version = '%s'\n" "${FFMPEG_VERSION}" >> /app/common/third_party_versions.py

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
