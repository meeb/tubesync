# syntax=docker/dockerfile:1
# check=error=true

ARG FFMPEG_VERSION="N"

ARG S6_VERSION="3.2.0.3"

ARG SHA256_S6_AMD64="01eb9a6dce10b5428655974f1903f48e7ba7074506dfb262e85ffab64a5498f2"
ARG SHA256_S6_ARM64="3a078ef3720a6f16cc93fbd748bdf1b17c9e9ff4ead67947e9565d93379d4168"
ARG SHA256_S6_NOARCH="ca79e39c9fea1ccfb6857a0eb13df7e7e12bc1b09454c4158b4075ade5a870ee"

ARG ALPINE_VERSION="latest"
ARG DEBIAN_VERSION="bookworm-slim"

ARG FFMPEG_PREFIX_FILE="ffmpeg-${FFMPEG_VERSION}"
ARG FFMPEG_SUFFIX_FILE=".tar.xz"

ARG FFMPEG_CHECKSUM_ALGORITHM="sha256"
ARG S6_CHECKSUM_ALGORITHM="sha256"


FROM debian:${DEBIAN_VERSION} AS tubesync-base

ARG TARGETARCH

ENV DEBIAN_FRONTEND="noninteractive" \
    APT_KEEP_ARCHIVES=1 \
    EDITOR="editor" \
    HOME="/root" \
    LANGUAGE="en_US.UTF-8" \
    LANG="en_US.UTF-8" \
    LC_ALL="en_US.UTF-8" \
    TERM="xterm" \
    # Do not include compiled byte-code
    PIP_NO_COMPILE=1 \
    PIP_ROOT_USER_ACTION='ignore'

RUN --mount=type=cache,id=apt-lib-cache-${TARGETARCH},sharing=private,target=/var/lib/apt \
    --mount=type=cache,id=apt-cache-cache,sharing=private,target=/var/cache/apt \
    # to be careful, ensure that these files aren't from a different architecture
    rm -f /var/cache/apt/*cache.bin ; \
    # Update from the network and keep cache
    rm -f /etc/apt/apt.conf.d/docker-clean ; \
    # Do not generate more /var/cache/apt/*cache.bin files
    # hopefully soon, this will be included in Debian images
    printf -- >| /etc/apt/apt.conf.d/docker-disable-pkgcache \
        'Dir::Cache::%spkgcache "";\n' '' src ; \
	chmod a+r /etc/apt/apt.conf.d/docker-disable-pkgcache ; \
    set -x && \
    apt-get update && \
    # Install locales
    LC_ALL='C.UTF-8' LANG='C.UTF-8' LANGUAGE='C.UTF-8' \
    apt-get -y --no-install-recommends install locales && \
    # localedef -v -i en_US -c -f UTF-8 -A /usr/share/locale/locale.alias en_US.UTF-8 && \
    printf -- "en_US.UTF-8 UTF-8\n" > /etc/locale.gen && \
    locale-gen && \
    # Clean up
    apt-get -y autopurge && \
    apt-get -y autoclean && \
    rm -f /var/cache/debconf/*.dat-old

FROM ghcr.io/astral-sh/uv:latest AS uv-binaries

FROM alpine:${ALPINE_VERSION} AS openresty-debian
ARG TARGETARCH
ARG DEBIAN_VERSION
ADD 'https://openresty.org/package/pubkey.gpg' '/downloaded/pubkey.gpg'
RUN set -eu ; \
    decide_arch() { \
        case "${TARGETARCH}" in \
            (amd64) printf -- '' ;; \
            (arm64) printf -- 'arm64/' ;; \
        esac ; \
    } ; \
    set -x ; \
    mkdir -v -p '/etc/apt/trusted.gpg.d' && \
    apk --no-cache --no-progress add cmd:gpg2 && \
    gpg2 --dearmor \
        -o '/etc/apt/trusted.gpg.d/openresty.gpg' \
        < '/downloaded/pubkey.gpg' && \
    mkdir -v -p '/etc/apt/sources.list.d' && \
    printf -- >| '/etc/apt/sources.list.d/openresty.list' \
        'deb http://openresty.org/package/%sdebian %s openresty' \
        "$(decide_arch)" "${DEBIAN_VERSION%-slim}"

FROM alpine:${ALPINE_VERSION} AS ffmpeg-download
ARG FFMPEG_DATE
ARG FFMPEG_VERSION
ARG FFMPEG_PREFIX_FILE
ARG FFMPEG_SUFFIX_FILE
ARG SHA256_FFMPEG_AMD64
ARG SHA256_FFMPEG_ARM64
ARG FFMPEG_CHECKSUM_ALGORITHM
ARG CHECKSUM_ALGORITHM="${FFMPEG_CHECKSUM_ALGORITHM}"
ARG FFMPEG_CHECKSUM_AMD64="${SHA256_FFMPEG_AMD64}"
ARG FFMPEG_CHECKSUM_ARM64="${SHA256_FFMPEG_ARM64}"

ARG FFMPEG_FILE_SUMS="checksums.${CHECKSUM_ALGORITHM}"
ARG FFMPEG_URL="https://github.com/yt-dlp/FFmpeg-Builds/releases/download/autobuild-${FFMPEG_DATE}"

ARG DESTDIR="/downloaded"
ARG TARGETARCH
ADD "${FFMPEG_URL}/${FFMPEG_FILE_SUMS}" "${DESTDIR}/"
RUN set -eu ; \
    apk --no-cache --no-progress add cmd:aria2c cmd:awk "cmd:${CHECKSUM_ALGORITHM}sum" ; \
\
    aria2c_options() { \
        algorithm="${CHECKSUM_ALGORITHM%[0-9]??}" ; \
        bytes="${CHECKSUM_ALGORITHM#${algorithm}}" ; \
        hash="$( awk -v fn="${1##*/}" '$0 ~ fn"$" { print $1; exit; }' "${DESTDIR}/${FFMPEG_FILE_SUMS}" )" ; \
\
        printf -- '\t%s\n' \
          'allow-overwrite=true' \
          'always-resume=false' \
          'check-integrity=true' \
          "checksum=${algorithm}-${bytes}=${hash}" \
          'max-connection-per-server=2' \
; \
        printf -- '\n' ; \
    } ; \
\
    decide_arch() { \
        case "${TARGETARCH}" in \
            (amd64) printf -- 'linux64' ;; \
            (arm64) printf -- 'linuxarm64' ;; \
        esac ; \
    } ; \
\
    FFMPEG_ARCH="$(decide_arch)" ; \
    FFMPEG_PREFIX_FILE="$( printf -- '%s' "${FFMPEG_PREFIX_FILE}" | cut -d '-' -f 1,2 )" ; \
    for url in $(awk ' \
      $2 ~ /^[*]?'"${FFMPEG_PREFIX_FILE}"'/ && /-'"${FFMPEG_ARCH}"'-/ { $1=""; print; } \
      ' "${DESTDIR}/${FFMPEG_FILE_SUMS}") ; \
    do \
        url="${FFMPEG_URL}/${url# }" ; \
        printf -- '%s\n' "${url}" ; \
        aria2c_options "${url}" ; \
        printf -- '\n' ; \
    done > /tmp/downloads ; \
    unset -v url ; \
\
    aria2c --no-conf=true \
      --dir /downloaded \
      --lowest-speed-limit='16K' \
      --show-console-readout=false \
      --summary-interval=0 \
      --input-file /tmp/downloads ; \
\
    decide_expected() { \
        case "${TARGETARCH}" in \
            (amd64) printf -- '%s' "${FFMPEG_CHECKSUM_AMD64}" ;; \
            (arm64) printf -- '%s' "${FFMPEG_CHECKSUM_ARM64}" ;; \
        esac ; \
    } ; \
\
    FFMPEG_HASH="$(decide_expected)" ; \
\
    cd "${DESTDIR}" ; \
    if [ -n "${FFMPEG_HASH}" ] ; \
    then \
        printf -- '%s *%s\n' "${FFMPEG_HASH}" "${FFMPEG_PREFIX_FILE}"*-"${FFMPEG_ARCH}"-*"${FFMPEG_SUFFIX_FILE}" >> /tmp/SUMS ; \
        "${CHECKSUM_ALGORITHM}sum" --check --warn --strict /tmp/SUMS || exit ; \
    fi ; \
    "${CHECKSUM_ALGORITHM}sum" --check --warn --strict --ignore-missing "${DESTDIR}/${FFMPEG_FILE_SUMS}" ; \
\
    mkdir -v -p "/verified/${TARGETARCH}" ; \
    ln -v "${FFMPEG_PREFIX_FILE}"*-"${FFMPEG_ARCH}"-*"${FFMPEG_SUFFIX_FILE}" "/verified/${TARGETARCH}/" ; \
    rm -rf "${DESTDIR}" ;

FROM alpine:${ALPINE_VERSION} AS ffmpeg-extracted
COPY --from=ffmpeg-download /verified /verified

ARG FFMPEG_PREFIX_FILE
ARG FFMPEG_SUFFIX_FILE
ARG TARGETARCH
RUN set -eux ; \
    mkdir -v /extracted ; \
    cd /extracted ; \
    ln -s "/verified/${TARGETARCH}"/"${FFMPEG_PREFIX_FILE}"*"${FFMPEG_SUFFIX_FILE}" "/tmp/ffmpeg${FFMPEG_SUFFIX_FILE}" ; \
    tar -tf "/tmp/ffmpeg${FFMPEG_SUFFIX_FILE}" | grep '/bin/\(ffmpeg\|ffprobe\)' > /tmp/files ; \
    tar -xop \
      --strip-components=2 \
      -f "/tmp/ffmpeg${FFMPEG_SUFFIX_FILE}" \
      -T /tmp/files ; \
\
    ls -AlR /extracted ;

FROM scratch AS ffmpeg
COPY --from=ffmpeg-extracted /extracted /usr/local/bin/

FROM alpine:${ALPINE_VERSION} AS s6-overlay-download
ARG S6_VERSION
ARG SHA256_S6_AMD64
ARG SHA256_S6_ARM64
ARG SHA256_S6_NOARCH

ARG DESTDIR="/downloaded"
ARG S6_CHECKSUM_ALGORITHM
ARG CHECKSUM_ALGORITHM="${S6_CHECKSUM_ALGORITHM}"

ARG S6_CHECKSUM_AMD64="${CHECKSUM_ALGORITHM}:${SHA256_S6_AMD64}"
ARG S6_CHECKSUM_ARM64="${CHECKSUM_ALGORITHM}:${SHA256_S6_ARM64}"
ARG S6_CHECKSUM_NOARCH="${CHECKSUM_ALGORITHM}:${SHA256_S6_NOARCH}"

ARG S6_OVERLAY_URL="https://github.com/just-containers/s6-overlay/releases/download/v${S6_VERSION}"
ARG S6_PREFIX_FILE="s6-overlay-"
ARG S6_SUFFIX_FILE=".tar.xz"

ARG S6_FILE_AMD64="${S6_PREFIX_FILE}x86_64${S6_SUFFIX_FILE}"
ARG S6_FILE_ARM64="${S6_PREFIX_FILE}aarch64${S6_SUFFIX_FILE}"
ARG S6_FILE_NOARCH="${S6_PREFIX_FILE}noarch${S6_SUFFIX_FILE}"

ADD "${S6_OVERLAY_URL}/${S6_FILE_AMD64}.${CHECKSUM_ALGORITHM}" "${DESTDIR}/"
ADD "${S6_OVERLAY_URL}/${S6_FILE_ARM64}.${CHECKSUM_ALGORITHM}" "${DESTDIR}/"
ADD "${S6_OVERLAY_URL}/${S6_FILE_NOARCH}.${CHECKSUM_ALGORITHM}" "${DESTDIR}/"

##ADD --checksum="${S6_CHECKSUM_AMD64}" "${S6_OVERLAY_URL}/${S6_FILE_AMD64}" "${DESTDIR}/"
##ADD --checksum="${S6_CHECKSUM_ARM64}" "${S6_OVERLAY_URL}/${S6_FILE_ARM64}" "${DESTDIR}/"
##ADD --checksum="${S6_CHECKSUM_NOARCH}" "${S6_OVERLAY_URL}/${S6_FILE_NOARCH}" "${DESTDIR}/"

# --checksum wasn't recognized, so use busybox to check the sums instead
ADD "${S6_OVERLAY_URL}/${S6_FILE_AMD64}" "${DESTDIR}/"
RUN set -eu ; checksum="${S6_CHECKSUM_AMD64}" ; file="${S6_FILE_AMD64}" ; cd "${DESTDIR}/" && \
    printf -- '%s *%s\n' "$(printf -- '%s' "${checksum}" | cut -d : -f 2-)" "${file}" | "${CHECKSUM_ALGORITHM}sum" -cw

ADD "${S6_OVERLAY_URL}/${S6_FILE_ARM64}" "${DESTDIR}/"
RUN set -eu ; checksum="${S6_CHECKSUM_ARM64}" ; file="${S6_FILE_ARM64}" ; cd "${DESTDIR}/" && \
    printf -- '%s *%s\n' "$(printf -- '%s' "${checksum}" | cut -d : -f 2-)" "${file}" | "${CHECKSUM_ALGORITHM}sum" -cw

ADD "${S6_OVERLAY_URL}/${S6_FILE_NOARCH}" "${DESTDIR}/"
RUN set -eu ; checksum="${S6_CHECKSUM_NOARCH}" ; file="${S6_FILE_NOARCH}" ; cd "${DESTDIR}/" && \
    printf -- '%s *%s\n' "$(printf -- '%s' "${checksum}" | cut -d : -f 2-)" "${file}" | "${CHECKSUM_ALGORITHM}sum" -cw

FROM alpine:${ALPINE_VERSION} AS s6-overlay-extracted
COPY --from=s6-overlay-download /downloaded /downloaded

ARG S6_CHECKSUM_ALGORITHM
ARG CHECKSUM_ALGORITHM="${S6_CHECKSUM_ALGORITHM}"

ARG TARGETARCH

RUN set -eu ; \
\
    decide_arch() { \
      local arg1 ; \
      arg1="${1:-$(uname -m)}" ; \
\
      case "${arg1}" in \
        (amd64) printf -- 'x86_64' ;; \
        (arm64) printf -- 'aarch64' ;; \
        (arm|armv7l) printf -- 'armhf' ;; \
        (*) printf -- '%s' "${arg1}" ;; \
      esac ; \
      unset -v arg1 ; \
    } ; \
\
    file_ext="${CHECKSUM_ALGORITHM}" ; \
    apk --no-cache --no-progress add "cmd:${CHECKSUM_ALGORITHM}sum" ; \
    mkdir -v /verified ; \
    cd /downloaded ; \
    for f in *."${file_ext}" ; \
    do \
      "${CHECKSUM_ALGORITHM}sum" --check --warn --strict "${f}" || exit ; \
      ln -v "${f%.${file_ext}}" /verified/ || exit ; \
    done ; \
    unset -v f file_ext ; \
\
    S6_ARCH="$(decide_arch "${TARGETARCH}")" ; \
    set -x ; \
    mkdir -v /s6-overlay-rootfs ; \
    cd /s6-overlay-rootfs ; \
    for f in /verified/*.tar* ; \
    do \
      case "${f}" in \
        (*-noarch.tar*|*-"${S6_ARCH}".tar*) \
          tar -xpf "${f}" || exit ;; \
      esac ; \
    done ; \
    set +x ; \
    unset -v f ;

FROM ghcr.io/tcely/s6-overlay:v${S6_VERSION} AS s6-overlay-img

FROM tubesync-base AS s6-overlay
COPY --from=s6-overlay-extracted /s6-overlay-rootfs /old
COPY --from=s6-overlay-img / /new
RUN echo Old tar: && tar -C /old -c . | sha256sum ; \
    echo New tar: && tar -C /new -c . | sha256sum ; \
    diff -r /old /new

FROM tubesync-base AS tubesync-uv
COPY --from=uv-binaries /uv /uvx /usr/local/bin/

FROM tubesync-base AS tubesync-openresty

COPY --from=openresty-debian \
    /etc/apt/trusted.gpg.d/openresty.gpg /etc/apt/trusted.gpg.d/openresty.gpg
COPY --from=openresty-debian \
    /etc/apt/sources.list.d/openresty.list /etc/apt/sources.list.d/openresty.list

RUN --mount=type=cache,id=apt-lib-cache-${TARGETARCH},sharing=private,target=/var/lib/apt \
    --mount=type=cache,id=apt-cache-cache,sharing=private,target=/var/cache/apt \
  set -x && \
  apt-get update && \
  apt-get -y --no-install-recommends install \
    nginx-common \
    openresty \
  && \
  # Clean up
  apt-get -y autopurge && \
  apt-get -y autoclean && \
  rm -v -f /var/cache/debconf/*.dat-old

FROM tubesync-base AS tubesync-nginx

RUN --mount=type=cache,id=apt-lib-cache-${TARGETARCH},sharing=private,target=/var/lib/apt \
    --mount=type=cache,id=apt-cache-cache,sharing=private,target=/var/cache/apt \
  set -x && \
  apt-get update && \
  apt-get -y --no-install-recommends install \
    nginx-light \
    libnginx-mod-http-lua \
  && \
  # openresty binary should still work
  ln -v -s -T ../sbin/nginx /usr/bin/openresty && \
  # Clean up
  apt-get -y autopurge && \
  apt-get -y autoclean && \
  rm -v -f /var/cache/debconf/*.dat-old

# The preference for openresty over nginx,
# is for the newer version.
FROM tubesync-openresty AS tubesync

ARG S6_VERSION

ARG FFMPEG_DATE
ARG FFMPEG_VERSION

ARG TARGETARCH

ENV S6_VERSION="${S6_VERSION}" \
    FFMPEG_DATE="${FFMPEG_DATE}" \
    FFMPEG_VERSION="${FFMPEG_VERSION}"

# Reminder: the SHELL handles all variables
RUN --mount=type=cache,id=apt-lib-cache-${TARGETARCH},sharing=private,target=/var/lib/apt \
    --mount=type=cache,id=apt-cache-cache,sharing=private,target=/var/cache/apt \
  set -x && \
  apt-get update && \
  # Install dependencies we keep
  # Install required distro packages
  apt-get -y --no-install-recommends install \
  libmariadb3 \
  libonig5 \
  pkgconf \
  python3 \
  python3-libsass \
  python3-pip-whl \
  python3-socks \
  curl \
  indent \
  less \
  lua-lpeg \
  tre-agrep \
  vis \
  xxd \
  && \
  # Link to the current python3 version
  ln -v -s -f -T "$(find /usr/local/lib -name 'python3.[0-9]*' -type d -printf '%P\n' | sort -r -V | head -n 1)" /usr/local/lib/python3 && \
  # Configure the editor alternatives
  touch /usr/local/bin/babi /bin/nano /usr/bin/vim.tiny && \
  update-alternatives --install /usr/bin/editor editor /usr/local/bin/babi 50 && \
  update-alternatives --install /usr/local/bin/nano nano /bin/nano 10 && \
  update-alternatives --install /usr/local/bin/nano nano /usr/local/bin/babi 20 && \
  update-alternatives --install /usr/local/bin/vim vim /usr/bin/vim.tiny 15 && \
  update-alternatives --install /usr/local/bin/vim vim /usr/bin/vis 35 && \
  rm -v /usr/local/bin/babi /bin/nano /usr/bin/vim.tiny && \
  # Create a 'app' user which the application will run as
  groupadd app && \
  useradd -M -d /app -s /bin/false -g app app && \
  # Clean up
  apt-get -y autopurge && \
  apt-get -y autoclean && \
  rm -v -f /var/cache/debconf/*.dat-old

# Install third party software
COPY --from=s6-overlay /old /
COPY --from=ffmpeg /usr/local/bin/ /usr/local/bin/

RUN --mount=type=cache,id=apt-lib-cache-${TARGETARCH},sharing=private,target=/var/lib/apt \
    --mount=type=cache,id=apt-cache-cache,sharing=private,target=/var/cache/apt \
    set -x && \
    apt-get update && \
    # Install file
    apt-get -y --no-install-recommends install file && \
    # Installed s6 (using COPY earlier)
    file -L /command/s6-overlay-suexec && \
    # Installed ffmpeg (using COPY earlier)
    /usr/local/bin/ffmpeg -version && \
    file /usr/local/bin/ff* && \
    # Clean up file
    apt-get -y autoremove --purge file && \
    # Clean up
    apt-get -y autopurge && \
    apt-get -y autoclean && \
    rm -v -f /var/cache/debconf/*.dat-old

# Switch workdir to the the app
WORKDIR /app

ARG YTDLP_DATE

# Set up the app
RUN --mount=type=tmpfs,target=/cache \
    --mount=type=cache,id=uv-cache,sharing=locked,target=/cache/uv \
    --mount=type=cache,id=pipenv-cache,sharing=locked,target=/cache/pipenv \
    --mount=type=cache,id=apt-lib-cache-${TARGETARCH},sharing=private,target=/var/lib/apt \
    --mount=type=cache,id=apt-cache-cache,sharing=private,target=/var/cache/apt \
    --mount=type=bind,source=/uv,target=/usr/local/bin/uv,from=uv-binaries \
    --mount=type=bind,source=Pipfile,target=/app/Pipfile \
  set -x && \
  apt-get update && \
  # Install required build packages
  apt-get -y --no-install-recommends install \
  default-libmysqlclient-dev \
  g++ \
  gcc \
  libjpeg-dev \
  libonig-dev \
  libpq-dev \
  libwebp-dev \
  make \
  postgresql-common \
  python3-dev \
  zlib1g-dev \
  && \
  # Install non-distro packages
  mkdir -v -p /cache/.home-directories && \
  cp -at /cache/.home-directories/ "${HOME}" && \
  HOME="/cache/.home-directories/${HOME#/}" \
  XDG_CACHE_HOME='/cache' \
  PIPENV_VERBOSITY=64 \
  PYTHONPYCACHEPREFIX=/cache/pycache \
  uv tool run --no-config --no-progress --no-managed-python -- \
    pipenv lock && \
  HOME="/cache/.home-directories/${HOME#/}" \
  XDG_CACHE_HOME='/cache' \
  PIPENV_VERBOSITY=1 \
  PYTHONPYCACHEPREFIX=/cache/pycache \
  uv tool run --no-config --no-progress --no-managed-python -- \
    pipenv requirements --from-pipfile --hash >| /cache/requirements.txt && \
  rm -v Pipfile.lock && \
  cat -v /cache/requirements.txt && \
  HOME="/cache/.home-directories/${HOME#/}" \
  UV_LINK_MODE='copy' \
  XDG_CACHE_HOME='/cache' \
  PYTHONPYCACHEPREFIX=/cache/pycache \
    uv --no-config --no-progress --no-managed-python \
    pip install --strict --system --break-system-packages \
    --requirements /cache/requirements.txt && \
  # remove the getpot_bgutil_script plugin
  find /usr/local/lib \
  -name 'getpot_bgutil_script.py' \
  -path '*/yt_dlp_plugins/extractor/getpot_bgutil_script.py' \
  -type f -print -delete \
  && \
  # Clean up
  apt-get -y autoremove --purge \
  default-libmysqlclient-dev \
  g++ \
  gcc \
  libjpeg-dev \
  libonig-dev \
  libpq-dev \
  libwebp-dev \
  make \
  postgresql-common \
  python3-dev \
  zlib1g-dev \
  && \
  apt-get -y autopurge && \
  apt-get -y autoclean && \
  LD_LIBRARY_PATH=/usr/local/lib/python3/dist-packages/pillow.libs:/usr/local/lib/python3/dist-packages/psycopg_binary.libs \
    find /usr/local/lib/python3/dist-packages/ \
      -name '*.so*' -print \
      -exec du -h '{}' ';' \
      -exec ldd '{}' ';' \
    >| /cache/python-shared-objects 2>&1 && \
  rm -v -f /var/cache/debconf/*.dat-old && \
  rm -v -rf /tmp/* ; \
  if grep >/dev/null -Fe ' => not found' /cache/python-shared-objects ; \
  then \
      cat -v /cache/python-shared-objects ; \
      printf -- 1>&2 '%s\n' \
        ERROR: '    An unresolved shared object was found.' ; \
      exit 1 ; \
  fi

# Copy root
COPY config/root /

# patch background_task
COPY patches/background_task/ \
    /usr/local/lib/python3/dist-packages/background_task/

# patch yt_dlp
COPY patches/yt_dlp/ \
    /usr/local/lib/python3/dist-packages/yt_dlp/

# Copy app
COPY tubesync /app
COPY tubesync/tubesync/local_settings.py.container /app/tubesync/local_settings.py

# Build app
RUN set -x && \
  # Make absolutely sure we didn't accidentally bundle a SQLite dev database
  test '!' -e /app/db.sqlite3 && \
  # Run any required app commands
  /usr/bin/python3 -B /app/manage.py compilescss && \
  /usr/bin/python3 -B /app/manage.py collectstatic --no-input --link && \
  rm -rf /config /downloads /run/app && \
  # Create config, downloads and run dirs
  mkdir -v -p /run/app && \
  mkdir -v -p /config/media /config/tasks && \
  mkdir -v -p /config/cache/pycache && \
  mkdir -v -p /downloads/audio && \
  mkdir -v -p /downloads/video && \
  # Check nginx configuration copied from config/root/etc
  openresty -c /etc/nginx/nginx.conf -e stderr -t && \
  # Append software versions
  ffmpeg_version=$(/usr/local/bin/ffmpeg -version | awk -v 'ev=31' '1 == NR && "ffmpeg" == $1 { print $3; ev=0; } END { exit ev; }') && \
  test -n "${ffmpeg_version}" && \
  printf -- "ffmpeg_version = '%s'\n" "${ffmpeg_version}" >> /app/common/third_party_versions.py

# Create a healthcheck
HEALTHCHECK --interval=1m --timeout=10s --start-period=3m CMD ["/app/healthcheck.py", "http://127.0.0.1:8080/healthcheck"]

# ENVS and ports
ENV PYTHONPATH="/app" \
    PYTHONPYCACHEPREFIX="/config/cache/pycache" \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME="0" \
    XDG_CACHE_HOME="/config/cache" \
    XDG_CONFIG_HOME="/config/tubesync" \
    XDG_STATE_HOME="/config/state"
EXPOSE 4848

# Volumes
VOLUME ["/config", "/downloads"]

# Entrypoint, start s6 init
ENTRYPOINT ["/init"]
