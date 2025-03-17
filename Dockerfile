# syntax=docker/dockerfile:1
# check=error=true

ARG FFMPEG_DATE="2025-03-04-15-43"
ARG FFMPEG_VERSION="N-118645-gf76195ff65"

ARG S6_VERSION="3.2.0.2"

ARG SHA256_S6_AMD64="59289456ab1761e277bd456a95e737c06b03ede99158beb24f12b165a904f478"
ARG SHA256_S6_ARM64="8b22a2eaca4bf0b27a43d36e65c89d2701738f628d1abd0cea5569619f66f785"
ARG SHA256_S6_NOARCH="6dbcde158a3e78b9bb141d7bcb5ccb421e563523babbe2c64470e76f4fd02dae"

ARG ALPINE_VERSION="latest"
ARG DEBIAN_VERSION="bookworm-slim"

ARG FFMPEG_PREFIX_FILE="ffmpeg-${FFMPEG_VERSION}"
ARG FFMPEG_SUFFIX_FILE=".tar.xz"

ARG FFMPEG_CHECKSUM_ALGORITHM="sha256"
ARG S6_CHECKSUM_ALGORITHM="sha256"

ARG CACHE_PATH="/cache"


FROM debian:${DEBIAN_VERSION} AS tubesync-base

ARG TARGETARCH

ENV DEBIAN_FRONTEND="noninteractive" \
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
    set -x && \
    apt-get update && \
    # Install locales
    apt-get -y --no-install-recommends install locales && \
    printf -- "en_US.UTF-8 UTF-8\n" > /etc/locale.gen && \
    locale-gen en_US.UTF-8 && \
    # Clean up
    apt-get -y autopurge && \
    apt-get -y autoclean

FROM debian:${DEBIAN_VERSION} AS tubesync-base

ARG TARGETARCH

ENV DEBIAN_FRONTEND="noninteractive" \
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
    set -x && \
    apt-get update && \
    # Install locales
    apt-get -y --no-install-recommends install locales && \
    printf -- "en_US.UTF-8 UTF-8\n" > /etc/locale.gen && \
    locale-gen en_US.UTF-8 && \
    # Clean up
    apt-get -y autopurge && \
    apt-get -y autoclean

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
        (armv7l) printf -- 'arm' ;; \
        (*) printf -- '%s' "${arg1}" ;; \
      esac ; \
      unset -v arg1 ; \
    } ; \
\
    apk --no-cache --no-progress add "cmd:${CHECKSUM_ALGORITHM}sum" ; \
    mkdir -v /verified ; \
    cd /downloaded ; \
    for f in *.sha256 ; \
    do \
      "${CHECKSUM_ALGORITHM}sum" --check --warn --strict "${f}" || exit ; \
      ln -v "${f%.sha256}" /verified/ || exit ; \
    done ; \
    unset -v f ; \
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

FROM scratch AS s6-overlay
COPY --from=s6-overlay-extracted /s6-overlay-rootfs /

FROM alpine:${ALPINE_VERSION} AS populate-apt-cache-dirs
ARG TARGETARCH
RUN --mount=type=bind,from=cache-tubesync,target=/restored \
    set -ex ; \
    mkdir -v -p /apt-cache-cache /apt-lib-cache ; \
    # restore `apt` files
    cp -at /apt-cache-cache/ /restored/apt-cache-cache/* || : ; \
    # to be careful, ensure that these files aren't from a different architecture
    rm -v -f /apt-cache-cache/*cache.bin ; \
    cp -at /apt-lib-cache/ "/restored/${TARGETARCH}/apt-lib-cache"/* || : ;

FROM alpine:${ALPINE_VERSION} AS populate-pipenv-cache-dir
RUN --mount=type=bind,from=cache-tubesync,target=/restored \
    set -x ; \
    cp -at / '/restored/pipenv-cache' || \
        mkdir -v /pipenv-cache ;

FROM alpine:${ALPINE_VERSION} AS populate-wormhole-dir
ARG TARGETARCH
RUN --mount=type=bind,from=cache-tubesync,target=/restored \
    set -x ; \
    cp -at / "/restored/${TARGETARCH}/wormhole" || \
        mkdir -v /wormhole ;

FROM tubesync-base AS tubesync

ARG S6_VERSION

ARG FFMPEG_DATE FFMPEG_VERSION

ENV S6_VERSION="${S6_VERSION}" \
    FFMPEG_DATE="${FFMPEG_DATE}" \
    FFMPEG_VERSION="${FFMPEG_VERSION}"

ARG TARGETARCH

# Reminder: the SHELL handles all variables
RUN --mount=type=cache,id=apt-lib-cache-${TARGETARCH},sharing=private,target=/var/lib/apt,source=/apt-lib-cache,from=populate-apt-cache-dirs \
    --mount=type=cache,id=apt-cache-cache,sharing=private,target=/var/cache/apt,source=/apt-cache-cache,from=populate-apt-cache-dirs \
  set -x && \
  apt-get update && \
  # Install dependencies we keep
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
  python3-libsass \
  python3-socks \
  python3-venv \
  python3-wheel \
  curl \
  less \
  && \
  # Link to the current python3 version
  ln -v -s -f -T "$(find /usr/local/lib -name 'python3.[0-9]*' -type d -printf '%P\n' | sort -r -V | head -n 1)" /usr/local/lib/python3 && \
  # Create a 'app' user which the application will run as
  groupadd app && \
  useradd -M -d /app -s /bin/false -g app app && \
  # Clean up
  apt-get -y autopurge && \
  apt-get -y autoclean

# Install third party software
COPY --from=s6-overlay / /
COPY --from=ffmpeg /usr/local/bin/ /usr/local/bin/

RUN --mount=type=cache,id=apt-lib-cache-${TARGETARCH},sharing=private,target=/var/lib/apt,source=/apt-lib-cache,from=populate-apt-cache-dirs \
    --mount=type=cache,id=apt-cache-cache,sharing=private,target=/var/cache/apt,source=/apt-cache-cache,from=populate-apt-cache-dirs \
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
    apt-get -y autoclean

# Switch workdir to the the app
WORKDIR /app

ARG CACHE_PATH

# Set up the app
RUN --mount=type=tmpfs,target=${CACHE_PATH} \
    --mount=type=cache,sharing=private,target=/var/lib/apt,source=/apt-lib-cache,from=populate-apt-cache-dirs \
    --mount=type=cache,sharing=private,target=/var/cache/apt,source=/apt-cache-cache,from=populate-apt-cache-dirs \
    --mount=type=cache,sharing=private,target=${CACHE_PATH}/pipenv,source=/pipenv-cache,from=populate-pipenv-cache-dir \
    --mount=type=cache,sharing=private,target=${CACHE_PATH}/wormhole,source=/wormhole,from=populate-wormhole-dir \
    --mount=type=secret,id=WORMHOLE_CODE,env=WORMHOLE_CODE \
    --mount=type=secret,id=WORMHOLE_RELAY,env=WORMHOLE_RELAY \
    --mount=type=secret,id=WORMHOLE_TRANSIT,env=WORMHOLE_TRANSIT \
    --mount=type=bind,source=Pipfile,target=/app/Pipfile \
  set -x && \
  # set up cache
  { \
    saved="${CACHE_PATH}/.saved" ; \
    pipenv_cache="${CACHE_PATH}/pipenv" ; \
    pycache="${CACHE_PATH}/pycache" ; \
    wormhole_venv="${CACHE_PATH}/wormhole" ; \
    mkdir -p "${saved}/${TARGETARCH}" ; \
    # keep the real HOME clean
    mkdir -p "${CACHE_PATH}/.home-directories" ; \
    cp -at "${CACHE_PATH}/.home-directories/" "${HOME}" && \
    HOME="${CACHE_PATH}/.home-directories/${HOME#/}" ; \
  } && \
  # install magic-wormhole
  ( test -d "${wormhole_venv}/bin" || \
    python3 -m venv --clear --system-site-packages --upgrade-deps "${wormhole_venv}" ; \
    . "${wormhole_venv}/bin/activate" || exit ; \
    test -x "${wormhole_venv}/bin/wormhole" || \
    pip install magic-wormhole ; \
  ) && \
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
  # Install non-distro packages
  XDG_CACHE_HOME="${CACHE_PATH}" \
  PIPENV_VERBOSITY=64 \
  PYTHONPYCACHEPREFIX="${pycache}" \
    pipenv install --system --skip-lock && \
  # Clean up
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
  apt-get -y autopurge && \
  apt-get -y autoclean && \
  # Save our saved directory to the cache directory on the runner
  test -z "${WORMHOLE_CODE}" || \
  ( set +x ; \
    . "${wormhole_venv}/bin/activate" && \
    set -x && \
    { \
      find /var/cache/apt/ -mindepth 1 -maxdepth 1 -name '*cache.bin' -delete || : ; \
    } && \
    cp -a /var/cache/apt "${saved}/apt-cache-cache" && \
    cp -a /var/lib/apt "${saved}/${TARGETARCH}/apt-lib-cache" && \
    cp -a "${pipenv_cache}" "${saved}/pipenv-cache" && \
    cp -a "${wormhole_venv}" "${saved}/${TARGETARCH}/" && \
    ls -al "${saved}" && ls -al "${saved}"/* && \
    ls -al "${saved}/${TARGETARCH}"/* && \
    if [ -n "${WORMHOLE_RELAY}" ] && [ -n "${WORMHOLE_TRANSIT}" ]; then \
      timeout -v -k 10m 1h wormhole \
        --appid TubeSync \
        --relay-url "${WORMHOLE_RELAY}" \
        --transit-helper "${WORMHOLE_TRANSIT}" \
        send \
        --code "${WORMHOLE_CODE}" \
        "${saved}" || : ; \
    else \
      timeout -v -k 10m 1h wormhole send \
        --code "${WORMHOLE_CODE}" \
        "${saved}" || : ; \
    fi ; \
  ) && \
  rm -v -rf /tmp/*

# Copy app
COPY tubesync /app
COPY tubesync/tubesync/local_settings.py.container /app/tubesync/local_settings.py

# patch background_task
COPY patches/background_task/ \
    /usr/local/lib/python3/dist-packages/background_task/

# patch yt_dlp
COPY patches/yt_dlp/ \
    /usr/local/lib/python3/dist-packages/yt_dlp/

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
  mkdir -v -p /downloads/video && \
  # Append software versions
  ffmpeg_version=$(/usr/local/bin/ffmpeg -version | awk -v 'ev=31' '1 == NR && "ffmpeg" == $1 { print $3; ev=0; } END { exit ev; }') && \
  test -n "${ffmpeg_version}" && \
  printf -- "ffmpeg_version = '%s'\n" "${ffmpeg_version}" >> /app/common/third_party_versions.py

# Copy root
COPY config/root /

# Check nginx configuration copied from config/root/etc
RUN set -x && \
    mkdir -v -p /config/log && \
    cp -a /var/log/nginx /config/log/ && \
    cp -v -p /config/log/nginx/access.log /config/log/nginx/access.log.gz && \
    nginx -t

# Create a healthcheck
HEALTHCHECK --interval=1m --timeout=10s --start-period=3m CMD ["/app/healthcheck.py", "http://127.0.0.1:8080/healthcheck"]

# ENVS and ports
ENV PYTHONPATH="/app" \
    PYTHONPYCACHEPREFIX="/config/cache/pycache" \
    S6_CMD_WAIT_FOR_SERVICES_MAXTIME="0" \
    XDG_CACHE_HOME="/config/cache"
EXPOSE 4848

# Volumes
VOLUME ["/config", "/downloads"]

# Entrypoint, start s6 init
ENTRYPOINT ["/init"]
