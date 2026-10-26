import os
import sys

# Forcing binaries to use system ffmpeg from PATH
os.environ["IMAGEIO_FFMPEG_EXE"] = "ffmpeg"
os.environ["FFMPEG_BINARY"] = "ffmpeg"

if getattr(sys, "frozen", False) and sys.platform.startswith("linux"):
    original_ld_path = os.environ.get("LD_LIBRARY_PATH_ORIG")
    if original_ld_path is not None:
        os.environ["LD_LIBRARY_PATH"] = original_ld_path
    else:
        os.environ.pop("LD_LIBRARY_PATH", None)
