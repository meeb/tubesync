# TubeSync

## Advanced usage guide - using exported cookies

This is a new feature in v0.10 of TubeSync and later. It allows you to use the cookies
file exported from your browser in "Netscape" format with TubeSync to authenticate
to YouTube. This can bypass some throttling, age restrictions and other blocks at
YouTube.

**IMPORTANT NOTE**: Using cookies exported from your browser that is authenticated
to YouTube identifes your Google account as using TubeSync. This may result in
potential account impacts and is entirely at your own risk. Do not use this
feature unless you really know what you're doing.

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
