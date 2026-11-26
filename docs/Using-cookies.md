# Using cookies

## Advanced usage guide - using exported cookies

This is a new feature in v0.10 of TubeSync and later. It allows you to use the cookies
file exported from your browser in "Netscape" format with TubeSync to authenticate
to YouTube. This can bypass some throttling, age restrictions and other blocks at
YouTube.

**IMPORTANT NOTE**: Using cookies exported from your browser that is authenticated
to YouTube identifes your Google account as using TubeSync. This may result in
potential account impacts and is entirely at your own risk. Do not use this
feature unless you really know what you're doing.

If you only need an account for age-restricted videos, see
[Using a cookies file only for age-restricted media](#using-a-cookies-file-only-for-age-restricted-media)
below.

## Requirements

Have a browser that supports exporting your cookies and be logged into YouTube.

## Steps

### 1. Export your cookies

You need to export cookies for youtube.com from your browser, you can either do
this manually or there are plug-ins to automate this for you. This file must be
in the "Netscape" cookie export format.

Save your cookies as a `cookies.txt` file.

### 2. Import into TubeSync

Drop the `cookies.txt` file into your TubeSync `config` directory.

If detected correctly, you will see something like this in the worker or container
logs:

```
YYYY-MM-DD HH:MM:SS,mmm [tubesync/INFO] [youtube-dl] using cookies.txt from: /config/cookies.txt
```

If you see that line it's working correctly.

If you see errors in your logs like this:

```
http.cookiejar.LoadError: '/config/cookies.txt' does not look like a Netscape format cookies file
```

Then your `cookies.txt` file was not generated or created correctly as it's not
in the required "Netscape" format. You can fix this by exporting your `cookies.txt`
in the correct "Netscape" format.

## Using a cookies file only for age-restricted media

This is available in v0.19.0 of TubeSync and later.

If the only reason you need an account is to get past age restrictions, you can
give TubeSync a second cookies file that it uses only after YouTube reports that
a video is age-restricted. All other requests keep using `cookies.txt` if you
have one, or no cookies if you do not. This keeps the account out of most
requests.

The **IMPORTANT NOTE** above applies to this file as well.

### How it works

- TubeSync first fetches the metadata or downloads the media as usual.
- If yt-dlp fails with an error that contains "confirm your age",
  "age-restricted" or "inappropriate for some users", and the age-restricted
  cookies file exists, TubeSync retries that request once with this file.
- The retry uses the age-restricted cookies instead of `cookies.txt`. The two
  files are not combined.
- TubeSync copies the file into a private temporary directory and gives the
  copy to yt-dlp. The copy is deleted after the retry. yt-dlp writes refreshed
  cookies back to the file it is given, so your file is never changed. This
  also means TubeSync does not keep these cookies up to date for you. When they
  expire, export a new file.
- Other errors, such as "Sign in to confirm you're not a bot", are not retried
  with this file.
- If the retry also fails, the task fails the same way it would without the
  file and is retried later.
- TubeSync checks for the file every time it is needed, so you do not need to
  restart the container after you add, replace or remove it.

### 1. Export the age-restricted cookies

Export the cookies for youtube.com from a browser that is logged in with the
account you want to use for age-restricted videos. As with `cookies.txt`, the
file must be in the "Netscape" cookie export format.

### 2. Add the file to TubeSync

Save the file as `cookies-age-restricted.txt` in the `tubesync` directory inside
your TubeSync `config` directory. In the container, the full path is:

```
/config/tubesync/cookies-age-restricted.txt
```

This is not the same directory as `cookies.txt`, which goes directly in the
`config` directory.

If you do not use the container, the default location is
`cookies-age-restricted.txt` next to `cookies.txt`. You can change it by setting
`AGE_RESTRICTED_COOKIES_FILE` in your `local_settings.py` file.

Nothing is logged until an age-restricted video is found. When TubeSync retries
with this file, you will see something like this in the worker or container
logs:

```
YYYY-MM-DD HH:MM:SS,mmm [tubesync/INFO] [youtube-dl] retrying with age restricted cookies from: /config/tubesync/cookies-age-restricted.txt
```
