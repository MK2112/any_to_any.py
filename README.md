# any_to_any.py - Media File Converter, Merger, Concatenator

Convert between various media file formats with this Python tool.<br>
Merge movie and audio files, concatenate files of the same type (image/audio/video), and more.

![screenshot](./img/Any-to-Any-Web.png)

## Supported Formats
**Audio:** MP2, MP3, FLAC, AAC, AC3, DTS, OGG, WMA, WAV, M4A, AIFF, WEBA, MKA, WV, CAF, TTA, M4B, EAC3, SPX<br>
**Image:** JPG, PNG, GIF, BMP, WEBP, TIFF, TGA, EPS<br>
**Video:** MP4, WEBM, MOV, MKV, AVI, WMV, FLV, MJPEG, M2TS, 3GP, ASF<br>
**Video Codecs:** AV1, VP9, H265, H264, XVID, MPEG4, THEORA

## Setup
1. **Clone/Download**:
   - Use `git clone` or download the latest version from this repository
2. **Python Version**:
   - Ensure you have Python `3.10.x` or higher installed
3. **Install Dependencies**:
   - Open a terminal in the project folder and run: `pip install -r requirements.txt`
4. **Running the Script**:
   Use Any_to_Any.py in either of two ways:
   - *Web Interface*
   - *Command Line Interface*

## Web Interface
- Start the web interface: `python any_to_any.py -w`
- Access the web view at `http://localhost:5000` via your browser
- Stop the web interface by pressing `CTRL+C` in the terminal

## Command Line Interface
You can structure a command in three fundamental ways:
- **Single File Processing**: Process a single file
   - You can convert,
   - You can't merge or concatenate with only one file.
- **Directory Processing**: Process all files in a directory
   - You can convert,
   - You can merge and concatenate files, if multiple are present.
- **Multi Directory/File Processing**: Process multiple files from different directories or multiple directories in full
   - You can convert,
   - You can merge or concatenate per input directory, not across them, not with single files. Yet.

### Parameters

| Command Argument                | Meaning |
| ----------------------- | ------- |
| `-h` or </br>`--help`        | List all available parameters, their description and default values, then exit. |
| `-i` or </br>`--input`       | Path to file itself or directory containing files to be converted. If not provided, the directory from where the script is called will be used. |
| `-f` or </br>`--format`      | Desired output file format, either `mp2`, `mp3`, `flac`, `wav`, `aac`, `aiff`, `ogg`, `m4a`, `ac3`, `dts`, `weba`, `wma`, `mka`, `wv`, `caf`, `tta`, `m4b`, `eac3`, `spx`, `jpg`, `png`, `gif`, `bmp`, `webp`, `tiff`, `tga`, `eps`, `mp4`, `webm`, `mov`, `mkv`, `avi`, `wmv`, `flv`, `m2ts`, `3gp`, `mjpeg`, `asf` or movie codecs like `h265`, `h264`, `xvid`, `mpeg4`, `av1`, `theora` and `vp9`. |
| `-o` or </br>`--output`      | Directory to save converted files into. Writing to the input file path, if none provided. |
| `-q` or </br>`--quality`     | Set output file quality, either `low`, `medium`, or `high`; default is same as input. |
| `-m` or </br>`--merge`       | Merge movie file with equally named audio file to become its audio track. |
| `-c` or </br>`--concat`      | Concatenate input files of the same type (images, audio, video) into one output file (e.g. `concatenated_video.mp4` for movie files, `concatenated_audio.mp3` for audio files). |
| `-w` or </br>`--web`         | Ignores all other arguments, starts browser + a web server at `http://localhost:5000`. |
| `-d` or </br>`--delete`      | Delete input files after conversion. |
| `-fps` or</br>`--framerate` | Set the framerate (fps) when converting to a movie format or codec; default maintains input fps. |

### Single File Processing
Convert WEBP to PNG:
```python
python any_to_any.py -i /path/to/file.webp -f png
```

Convert MP4 to MP3, delete MP4 file afterwards:
```python
python any_to_any.py -i /path/to/file.mp4 -f mp3 -d
```

Convert MP3 to M4A, set conversion quality to high, delete MP3 source file afterwards:
```python
python any_to_any.py -i /path/to/file.mp3 -f m4a -q high -d
```

### Directory Processing
Directory Processing is useful when you want to convert all files in a directory to another format:

Convert all WEBP files to PNG:
```python
python any_to_any.py -i /path/to/webp-folder -f png
```

Convert all MP4 files to MP3, save to a different directory, set conversion quality to high, delete mp4 files afterwards:
```python
python any_to_any.py -i /path/to/mp4-folder -o /path/to/save/folder -f mp3 -q high -d
```

Merge MP4 files with respective, equally named MP3 files:
```python
python any_to_any.py -i /path/to/folder -o /path/to/save/folder -m -d
```

Concatenate MP4 files:
```python
python any_to_any.py -i /path/to/mp4-folder -o /path/to/save/folder -c -d
```

### Multi Directory/File Processing
You can also process multiple individual files or multiple directories at once.<br>
Note that only one output directory can be specified (omitting the `-o` parameter works and will write to the input file paths).
```python
python any_to_any.py -i -1 /path/to/file1.mp4 -2 /path/to/mp4-folder -o /path/to/output-folder -f mp3
```

## License
This project is licensed under the MIT License, granting users the freedom to modify and distribute the codebase.

## Contributions
Contributions and feedback are welcome. Feel free to open issues or pull requests.

## Disclaimer
This script is provided as-is, without any warranties or guarantees.<br>
Users are responsible for ensuring compliance with applicable laws and regulations.
