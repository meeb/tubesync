## General information about tokens

- https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide

## YouTube Proof-of-Origin Token plugin

To generate tokens TubeSync is using a plugin for `yt-dlp` from:
* https://github.com/Brainicism/bgutil-ytdlp-pot-provider/tree/1.2.2/plugin/yt_dlp_plugins/extractor/

#### Addition of plugin support

Support for using the plugin was added in: https://github.com/meeb/tubesync/pull/1005

#### Plugin web server URL

This plugin communicates with a web service to retrieve tokens, for which it uses a default URL of: `http://127.0.0.1:4416`

Because for TubeSync `openresty` is what most users will connect to with their web browser, the [configuration](../config/root/etc/nginx/token_server.conf) to listen on port `4416` has been added.

If you are using another web server instead, you should configure similar proxying of the requests, or configure a different URL for the plugin to use.

> [!TIP]
> You can set the base URL that the plugin tries to access with a custom `local_settings.py` file.
> 
> ```python
> YOUTUBE_DEFAULTS = {
>     'extractor_args': {
>         'youtubepot-bgutilhttp': {
>             'base_url': ['http://127.0.0.1:4416'],
>         },
>     },
>     # ... all the other yt_dlp settings
> }
> ```

#### Running the web service container the plugin communicates with

Docker image: `brainicism/bgutil-ytdlp-pot-provider:1.2.2`

```sh
$ docker run -d \
    --name bgutil-ytdlp-pot-service \
    -p 4416:4416 \
    --restart unless-stopped \
    brainicism/bgutil-ytdlp-pot-provider:1.2.2
```

#### Configure the plugin using environment variables

Because most users do not already have a custom `local_settings.py` file, and are not using a custom web server, an easier way to configure the plugin was developed.

> [!NOTE]
> You will need to add a new container so that your `TubeSync` container can access it.

After that is running, you can set the new environment variables to use the web services provided by that container:

```sh
$ TUBESYNC_POT_PORT=4416
$ export TUBESYNC_POT_PORT
$ TUBESYNC_POT_IPADDR=[Whatever IP you are using]
$ export TUBESYNC_POT_IPADDR
```

> [!IMPORTANT]
> Don't forget to add `-e TUBESYNC_POT_IPADDR -e TUBESYNC_POT_PORT` to the `docker run` command that you are using with `TubeSync` as well.

> [!TIP]
> Setting `TUBESYNC_POT_HTTPS` to `True` will connect using `https://`[^1] instead of `http://`.

[^1]: Setting up valid certificates for the web service is outside the scope of this guide.

#### Using the `--link` flag with `docker run`

When you have both containers on the same `docker` host, it can be very convenient to use this method.

Environment variables are automatically created by `docker`, and support for using those was included.

For a web service container named `bgutil-ytdlp-pot-service` you would add this `--link` option to your `docker run` command for TubeSync:

```sh
$ docker run --link 'bgutil-ytdlp-pot-service:POTServer' # everything else
```

#### Checking that things are working

The web service provides a `/ping` endpoint.

```sh
$ no_proxy='127.0.0.1' curl 'http://127.0.0.1:4416/ping' ; echo
{"token_ttl_hours":6,"server_uptime":1633.034876421,"version":"0.8.4"}
```

If the `curl` command above works from inside the TubeSync container, then the web server configuration is proxying the requests as expected.

When it is not configured, the same `/ping` request receives a HTTP 502 error.

#### More information about the web service the plugin uses

Server:
* [Dockerfile](https://github.com/Brainicism/bgutil-ytdlp-pot-provider/blob/master/server/Dockerfile)
* [main](https://github.com/Brainicism/bgutil-ytdlp-pot-provider/blob/master/server/src/main.ts)


#### All of the environment variables available

Added environment variables:

- TUBESYNC_POT_IPADDR
- TUBESYNC_POT_PORT
- TUBESYNC_POT_HTTPS (use https:// when set)

