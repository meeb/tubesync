After #1005 was merged, you are welcome to try the new support for the plugin.

The implementation mostly went as I planned, except for needing to use an IP address.

> [!TIP]
> You can skip all of this `nginx` mess entirely by configuring the base URL the plugin tries to access in the settings file.
> 
> ```python
> YOUTUBE_DEFAULTS = {
>     'extractor_args': {
>         # old plugin versions looked under 'youtube'
>         'youtube': {
>             'getpot_bgutil_baseurl': ['http://127.0.0.1:4416'],
>         },
>         'youtubepot-bgutilhttp': {
>             'baseurl': ['http://127.0.0.1:4416'],
>         },
>     },
>     # ... all the other yt_dlp settings
> }
> ```

Most users won't want to do that much work, so the environment variables will make it simpler to get everything working together quickly.

> [!NOTE]
> You will need to add a new container so that your `TubeSync` container can access it:
> 
> ```sh
> $ docker run --name bgutil-ytdlp-pot-provider -d \
>     -p 4416:4416 --restart unless-stopped --pull always \
>     brainicism/bgutil-ytdlp-pot-provider
> ```

After that is running, you can set the new environment variables to use the web services provided by that container:

```sh
$ TUBESYNC_POT_PORT=4416
$ export TUBESYNC_POT_PORT
$ TUBESYNC_POT_IPADDR=[Whatever IP you are using]
$ export TUBESYNC_POT_IPADDR
```

> [!IMPORTANT]
> Don't forget to add `-e TUBESYNC_POT_IPADDR -e TUBESYNC_POT_PORT` to the `docker run` command that you are using with `TubeSync` as well.

