from yt_dlp.compat.compat_utils import passthrough_module

passthrough_module(__name__, '.patch')
del passthrough_module

