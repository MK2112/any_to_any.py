# any_to_any.py - Media File Converter, Merger, Concatenator

Convert between various media file formats with this Python tool.<br>
Merge movie and audio files, concatenate files of the same type (image/audio/video), and more.

![screenshot](./img/Any-to-Any-Web.png)

## Supported Formats
**Audio:** MP3, FLAC, WAV, AAC, AIFF, OGG, M4A, WEBA, WMA, AC3, DTS<br> 
**Image:** JPEG, PNG, GIF, BMP, WEBP<br>
**Video:** MP4, WEBM, MOV, MKV, AVI, WMV, FLV, MJPEG<br>
**Video Codecs:** H265, H264, XVID, MPEG4, AV1, VP9

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
All parameters are optional:
- `-h` or `--help`: List all available parameters, their description and default values, then exit.
- `-i` or `--input`: Path to file itself or directory containing files to be converted. If not provided, the directory from where script is called will be used.
- `-f` or `--format`: File format of desired output, either `mp3`, `flac`, `wav`, `aac`, `aiff`, `ogg`, `m4a`, `ac3`, `dts`, `weba`, `wma`, `jpeg`, `png`, `gif`, `bmp`, `webp`, `mp4`, `webm`, `mov`, `mkv`, `avi`,  `wmv`, `flv`, `mjpeg` or mp4 codecs like `h265`, `h264`, `xvid`, `mpeg4`, `av1` and `vp9`.
- `-o` or `--output`: Directory to save converted files. If not provided, it will write to the input file path.
- `-q` or `--quality`: Set the quality of the output file, either `low`, `medium`, or `high`; default is same as input.
- `-m` or `--merge`: Per movie file, merge to movie with equally named audio file as its audio track.
- `-c` or `--concat`: Concatenate input files of the same type (images, audio, video) into one output file (e.g. `concatenated_video.mp4` for movie files, `concatenated_audio.mp3` for audio files).
- `-w` or `--web`: Ignores all other arguments, starts a web server + browser at `http://localhost:5000`.
- `-d` or `--delete`: Delete input files after conversion.
- `-fps` or `--framerate`: Set the framerate (fps) when converting to a movie format or codec; default maintains input fps.

### Single File Processing
Here are three examples of how to convert a single file to another format:

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
