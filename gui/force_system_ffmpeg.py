import os

# Forcing binaries to use system ffmpeg from PATH
os.environ["IMAGEIO_FFMPEG_EXE"] = "ffmpeg"
os.environ["FFMPEG_BINARY"] = "ffmpeg"
