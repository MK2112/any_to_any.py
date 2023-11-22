# any_to_any.py - Convert Media Files

This Python script helps you convert between various media file formats.

## Supported Formats
**Audio:** MP3, FLAC, WAV, OGG, M4A, WEBA<br> 
**Image:** PNG, GIF, BMP, WEBP<br>
**Video:** MP4, WEBM, MOV, MKV, AVI<br>
**Video Codecs:** H265, H264, XVID, MPEG4, AV1, VP9

## Usage
1. **Download/Clone**:
   - Either download the most recent version from this Git repository directly, or use `git clone` to do so
2. **Python Version**:
   - Ensure you have Python 3.x installed on your system. If not, you can download it from the official [Python website](https://www.python.org/downloads/).
3. **Install MoviePy**:
   - This script relies on `moviepy` and `pillow`. Install them via terminal:<br>`pip install moviepy pillow`
4. **Running the Script**:
    - Use the following command to convert e.g. MP4 files MP3:<br>`python any_to_any.py -i /path/to/mp4s -o /path/to/save/files -f mp3 -q high -d`
    - Use the following command to merge e.g. MP4 files with equally named MP3 files:<br>`python any_to_any.py -i /path/to/files -o /path/to/save/files -m -d`
    - Parameters:
      - `-i` or `--input` (optional): Directory containing MP4 files to be converted. If not provided, the directory from where script is called will be used
      - `-f` or `--format` (optional): File format of desired output, either `mp3`, `flac`, `wav`, `ogg`, `m4a`, `weba`, `png`, `gif`, `bmp`, `webp`, `mp4`, `webm`, `mov`, `mkv`, `avi`, or mp4 codecs like `h265`, `h264`, `xvid`, `mpeg4`, `av1` and `vp9`
      - `-o` or `--output` (optional): Directory to save converted files. If not provided, it will write to the input file path.
      - `-q` or `--quality` (optional): Set the quality of the output file, either `low`, `medium`, or `high`; default is same as input.
      - `-m` or `--merge` (optional): Per movie file, merge to movie with equally named audio file as its audio track.
      - `-d` or `--delete` (optional): Delete input files after conversion.
      - `-fps` or `--framerate` (optional): Set the framerate (fps) when converting to a movie format or codec; default maintains input fps.
   - Interaction via Web Browser is in the making, for now it's CLI

### License
This project is licensed under the MIT License, granting users the freedom to modify and distribute the codebase.

### Contributions
Contributions and feedback are welcome. Feel free to open issues or pull requests.

### Disclaimer
This script is provided as-is, without any warranties or guarantees.<br>
Users are responsible for ensuring compliance with applicable laws and regulations.
