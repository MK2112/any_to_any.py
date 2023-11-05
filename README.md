# mp4-to-any.py - Convert MP4

This Python script helps you convert MP4 files to various different formats.<br>
It provides a light-weight solution, addressing shortcomings of certain proprietary software options.

## Supported Formats
**Audio:** MP3, FLAC, WAV, OGG<br> 
**Image:** PNG, GIF, BMP<br>
**Video:** WebM, MOV, MKV, AVI<br>
**Mp4 Codecs:** H265, H264, XVID, MPEG4

## Usage
1. **Download/Clone**:
   - Either download the most recent version from this Git repository directly, or use `git clone` to do so
2. **Python Version**:
   - Ensure you have Python 3.x installed on your system. If not, you can download it from the official [Python website](https://www.python.org/downloads/).
3. **Install MoviePy**:
   - This script relies on the `moviepy` library for video processing. Install it via command prompt/terminal:<br>`pip install moviepy`
4. **Running the Script**:
    - Use the following command to convert MP4 files to MP3:<br>`python mp4-to-any.py -i /path/to/mp4s -o /path/to/save/files -f mp3 -d`
    - Parameters:
      - `-i` or `--input` (optional): Directory containing MP4 files to be converted. If not provided, the directory from where script is called will be used
      - `-f` or `--format` (required): File format of desired output, either `mp3`, `png`, `gif`, `webm`, `flac`, `avi`, `bmp`, or mp4 codecs like `h265`, `h264`, `xvid` and `mpeg4`.
      - `-o` or `--output` (optional): Directory to save MP3 files. If not provided, it will write to the MP4 path.
      - `-d` or `--delete` (optional): Delete MP4 files after conversion.
      - `-fps` or `--framerate` (optional): Designate the framerate (fps) when converting to a movie format or codec; default maintains input fps.
   - Interaction via Web Browser is in the making, for now it's CLI

### License
This project is licensed under the MIT License, granting users the freedom to modify and distribute the codebase.

### Contributions
Contributions and feedback are welcome. Feel free to open issues or pull requests.

### Disclaimer
This script is provided as-is, without any warranties or guarantees.<br>
Users are responsible for ensuring compliance with applicable laws and regulations.
