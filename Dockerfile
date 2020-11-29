FROM debian:buster-slim

ARG DEBIAN_FRONTEND="noninteractive"

# Third party software versions
ARG FFMPEG_VERSION="4.3.1"
ENV FFMPEG_EXPECTED_MD5="ee235393ec7778279144ee6cbdd9eb64"
ENV FFMPEG_TARBALL="https://johnvansickle.com/ffmpeg/releases/ffmpeg-${FFMPEG_VERSION}-amd64-static.tar.xz"

# Install third party software
RUN set -x && \
    # Install required distro packages
    apt-get update && \
    apt-get -y --no-install-recommends install curl xz-utils ca-certificates binutils && \
    # Install ffmpeg
    curl -L ${FFMPEG_TARBALL} --output /tmp/ffmpeg-${FFMPEG_VERSION}-amd64-static.tar.xz && \
    echo "${FFMPEG_EXPECTED_MD5}  tmp/ffmpeg-${FFMPEG_VERSION}-amd64-static.tar.xz" | md5sum -c - && \
    xz --decompress /tmp/ffmpeg-${FFMPEG_VERSION}-amd64-static.tar.xz && \
    tar -xvf /tmp/ffmpeg-${FFMPEG_VERSION}-amd64-static.tar -C /tmp && \
    ls -lat /tmp/ffmpeg-4.3.1-amd64-static && \
    install -v -s -g root -o root -m 0755 -s /tmp/ffmpeg-${FFMPEG_VERSION}-amd64-static/ffmpeg -t /usr/local/bin && \
    # Clean up
    rm -rf /tmp/ffmpeg-${FFMPEG_VERSION}-amd64-static.tar && \
    rm -rf /tmp/ffmpeg-${FFMPEG_VERSION}-amd64-static && \
    apt-get -y autoremove --purge curl xz-utils binutils

# Defaults
ARG default_uid="10000"
ARG default_gid="10000"

# Copy app
COPY app /app
COPY app/tubesync/local_settings.py.container /app/tubesync/local_settings.py

# Append container bundled software versions
RUN echo "ffmpeg_version = '${FFMPEG_VERSION}-static'" >> /app/common/third_party_versions.py

# Add Pipfiles
COPY Pipfile /app/Pipfile
COPY Pipfile.lock /app/Pipfile.lock

# Switch workdir to the the app
WORKDIR /app

# Set up the app
ENV UID="${default_uid}"
ENV GID="${default_gid}"
RUN set -x && \
  # Install required distro packages
  apt-get -y --no-install-recommends install python3 python3-setuptools python3-pip python3-dev gcc make && \
  # Install wheel which is required for pipenv
  pip3 --disable-pip-version-check install wheel && \
  # Then install pipenv
  pip3 --disable-pip-version-check install pipenv && \
  # Create a 'www' user which the workers drop to
  groupadd -g ${GID} www && \
  useradd -M -d /app -s /bin/false -u ${UID} -g www www && \
  # Install non-distro packages
  pipenv install --system  && \
  # Make absolutely sure we didn't accidentally bundle a SQLite dev database
  rm -rf /app/db.sqlite3 && \
  # Create config, downloads and run dirs we can write to
  mkdir -p /run/www && \
  chown -R www:www /run/www && \
  chmod -R 0700 /run/www && \
  mkdir -p /config/media && \
  chown -R www:www /config && \
  chmod -R 0755 /config && \
  mkdir -p /downloads/{audio,video} && \
  chown -R www:www /downloads && \
  chmod -R 0755 /downloads && \
  # Reset permissions
  mkdir -p /app/static && \
  chown -R root:www /app && \
  chown -R www:www /app/common/static && \
  chown -R www:www /app/static && \
  chmod -R 0750 /app && \
  find /app -type f -exec chmod 640 {} \; && \
  chmod 0750 /app/entrypoint.sh && \
  # Clean up
  rm /app/Pipfile && \
  rm /app/Pipfile.lock && \
  pipenv --clear && \
  pip3 --disable-pip-version-check uninstall -y pipenv wheel virtualenv && \
  apt-get -y autoremove --purge python3-pip python3-dev gcc make && \
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

# Create a healthcheck
HEALTHCHECK --interval=1m --timeout=10s CMD /app/healthcheck.py http://127.0.0.1:8080/healthcheck

# Drop to the www user
USER www

# ENVS and ports
ENV PYTHONPATH "/app:${PYTHONPATH}"
EXPOSE 8080

# Entrypoint
ENTRYPOINT ["/app/entrypoint.sh"]

# Run gunicorn
CMD ["/usr/local/bin/gunicorn", "-c", "/app/tubesync/gunicorn.py", "--capture-output", "tubesync.wsgi:application"]
