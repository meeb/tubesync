# TubeSync

## Advanced usage guide - Writing Custom Filters

Tubesync provides ways to filter media based on age, title string, and 
duration. This is sufficient for most use cases, but there more complicated
use cases that can't easily be anticipated. Custom filters allow you to 
write some Python code to easily add your own logic into the filtering.

Any call to an external API, or that requires access the metadata of the
media item, will be much slower than the checks for title/age/duration. So
this custom filter is only called if the other checks have already passed.
You should also be aware that external API calls will significantly slow
down the check process, and for large channels or databases this could be
an issue.

### How to use
1. Copy `tubesync/sync/overrides/custom_filter.py` to your local computer
2. Make your code changes to the `filter_custom` function in that file. Simply return `True` to skip downloading the item, and `False` to allow it to download
3. Override `tubesync/sync/overrides/custom_filter.py` in your docker container.

#### Docker run
Include `-v /some/directory/tubesync-overrides:/app/sync/overrides` in your docker run
command, pointing to the location of your override file.

#### Docker Compose
Include a volume line pointing to the location of your override file.
e.g.
```yaml
services:
  tubesync:
    image: ghcr.io/meeb/tubesync:latest
    container_name: tubesync
    restart: unless-stopped
    ports:
      - 4848:4848
    volumes:
      - /some/directory/tubesync-config:/config
      - /some/directory/tubesync-downloads:/downloads
      - /some/directory/tubesync-overrides:/app/sync/overrides
```