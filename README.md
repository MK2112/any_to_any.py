# any-to-any.py - Convert Media Files

This Python script helps you convert between various media file formats.

## Supported Formats
**Audio:** MP3, FLAC, WAV, OGG<br> 
**Image:** PNG, GIF, BMP<br>
**Video:** MP4, WebM, MOV, MKV, AVI<br>
**Mp4 Codecs:** H265, H264, XVID, MPEG4

## Usage
1. **Download/Clone**:
   - Either download the most recent version from this Git repository directly, or use `git clone` to do so
2. **Python Version**:
   - Ensure you have Python 3.x installed on your system. If not, you can download it from the official [Python website](https://www.python.org/downloads/).
3. **Install MoviePy**:
   - This script relies on the libraries `moviepy` and `pillow`. Install ithem via terminal:<br>`pip install moviepy pillow`
4. **Running the Script**:
    - Use the following command to convert e.g. MP4 files to MP3:<br>`python any-to-any.py -i /path/to/mp4s -o /path/to/save/files -f mp3 -d`
    - Parameters:
      - `-i` or `--input` (optional): Directory containing MP4 files to be converted. If not provided, the directory from where script is called will be used
      - `-f` or `--format` (required): File format of desired output, either `mp3`, `flac`, `wav`, `ogg`, `png`, `gif`, `bmp`, `mp4`, `webm`, `mov`, `mkv`, `avi`, or mp4 codecs like `h265`, `h264`, `xvid` and `mpeg4`.
      - `-o` or `--output` (optional): Directory to save converted files. If not provided, it will write to the input file path.
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
