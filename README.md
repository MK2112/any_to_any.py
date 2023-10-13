# mp4-to-any.py - Convert MP4 to MP3/PNG/GIF

This Python script helps you convert MP4 files to MP3/PNG/GIF format.<br>
It provides a cost-free and versatile solution, addressing shortcomings of certain proprietary software options.
E.g. I used it mainly to dissect camera input into frames for ML/AI training. Good stuff.

## Key Features
- **Efficiency**: A tool for swift file format transformation. Nothing more. Nothing less.
- **Cost-Free**: Eliminates the need for expensive proprietary software to do just the same.

## Usage
1. **Download/Clone**:
   - Either download the most recent version from this Git repository directly, or use `git clone` to do so
2. **Python Version**:
   - Ensure you have Python 3.x installed on your system. If not, you can download it from the official [Python website](https://www.python.org/downloads/).
3. **Install MoviePy**:
   - This script relies on the `moviepy` library for video processing. Install it via command prompt/terminal: `pip install moviepy`
4. **Running the Script**:
    - Use the following command to convert MP4 files to MP3: `python mp4-to-any.py -i /path/to/mp4s -o /path/to/save/files -d`
    - Parameters:
      - `-i` or `--input`: Directory containing MP4 files to be converted (required).
      - `-f` or `--format`: File format of desired output, either `mp3`, `gif` or `png` (required)
      - `-o` or `--output`: Directory to save MP3 files. If not provided, it will write to the MP4 path.
      - `-d` or `--delete`: Delete MP4 files after conversion (optional).

### License
This project is licensed under the MIT License, granting users the freedom to modify and distribute the codebase.

### Contributions
Contributions and feedback are welcome. Feel free to open issues or pull requests.

### Disclaimer
This script is provided as-is, without any warranties or guarantees.<br>
Users are responsible for ensuring compliance with applicable laws and regulations.
