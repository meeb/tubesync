## Integrating with Plex

#### Requirements:
- Plex
- ZeroQI's [YouTube-Agent](https://github.com/ZeroQI/YouTube-Agent.bundle)
- ZeroQI's [Absolute Series Scanner](https://github.com/ZeroQI/Absolute-Series-Scanner)

#### TubeSync settings for the source:
- directory ends with ` [youtube2-UCxxxxx]`
- media format ends with `[{key}].{ext}`
- write JSON (`.info.json`) files
- write NFO
- copy thumbnail

#### An example

> I recommend ZeroQI's [YouTube-Agent](https://github.com/ZeroQI/YouTube-Agent.bundle) and [Absolute Series Scanner](https://github.com/ZeroQI/Absolute-Series-Scanner). It downloads descriptions and tags and does a nice job of title recognition. Takes a bit more setup in Tubesync. You will need to rename folders to be `Channel Name [youtube-UCXXXXX]`. If your channels upload more than once a day, I recommend `Channel Name [youtube2-UCXXXXX]`. I default to "youtube2" for safety. Playlists should use `[youtube-PLXXXXX]` It will organize your episodes into seasons by Year. Episodes are numbered MDDMMSS (no leading 0 for month). For an episode today, `S2025E6251035`. I also recommend changing your file naming scheme to be `{uploader} - {yyyy_mm_dd} - {title_full} [{key}].{ext}`. The `[key]` part is required for metadata recognition. Your scheme may vary if on Windows. I am using Linux.
> 
> To setup in Plex after installation, create a Youtube library as TV Show. Add your Tubesync directory and set the Scanner to Absolute Series Scanner and set the Agent to YouTubeSeries. It is also best if you create your own Youtube API key to pull metadata. ZeroQi walks you through how to do that. Hope this helps someone.
> 
> ![Image](https://github.com/user-attachments/assets/e0f651df-6f06-4d95-b211-bf897573cb47)
> ![Image](https://github.com/user-attachments/assets/acabb5d8-d4d1-4b48-90aa-53ca87c3033c)
> ![Image](https://github.com/user-attachments/assets/2338b13b-5d23-4c3b-b24e-989612131b32)
> ![Image](https://github.com/user-attachments/assets/ad7decd3-133c-4111-a2b0-e912ad7487ea)` 

 _Originally posted by @mikeyounge in [#1138](https://github.com/meeb/tubesync/issues/1138#issuecomment-3005486972)_
