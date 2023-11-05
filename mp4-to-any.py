import os
import argparse
from moviepy.editor import VideoFileClip


class Mp4ToAny:
    """
    Taking an input directory of mp4 files, convert them to a multitude of formats using moviepy.
    Interact with the script using the command line arguments defined at the bottom of this file.
    """

    def __init__(self):
        self._supported_formats = {
            'audio': {
                'mp3': 'libmp3lame',
                'flac': 'flac',
                'ogg': 'libvorbis',
                'wav': 'pcm_s16le',
            },
            'image': {
                'gif': self.to_gif,
                'png': self.to_frames_png,
                'bmp': self.to_bmp,
            },
            'movie': {
                'webm': (self.to_movie, 'libvpx'),
                'mov': (self.to_movie, 'libx264'),
                'mkv': (self.to_movie, 'libx264'),
                'avi': (self.to_movie, 'libx264'),
            },
            'movie_codecs': {
                'h265': (self.to_codec, 'libx265'),
                'h264': (self.to_codec, 'libx264'),
                'xvid': (self.to_codec, 'libxvid'),
                'mpeg4': (self.to_codec, 'mpeg4'),
            },
        }

        self.formats_summary = [format for formats in self._supported_formats.values() for format in formats.keys()]


    # Single point of exit for the script
    def end_with_msg(self, msg):
        print(msg)
        exit(1)


    # Main function to convert mp4 files to defined formats
    def convert(self, input, format, output, framerate, delete):
        self.input = input if input is not None else os.getcwd()
        self.format = format
        self.output = output
        self.framerate = framerate
        self.delete = delete
        
        # Check if value associated to format is tuple/string or function to call specific conversion
        if isinstance(self._supported_formats['movie'][self.format], tuple):
            self._supported_formats['movie'][self.format][0](self.format, self._supported_formats['movie'][self.format][1], self._get_mp4_paths())
        elif isinstance(self._supported_formats['movie_codecs'][self.format], tuple):
            self._supported_formats['movie_codecs'][self.format][0](self.format, self._supported_formats['movie_codecs'][self.format][1], self._get_mp4_paths())
        elif isinstance(self._supported_formats['image'][self.format], str):
            self._supported_formats['image'][self.format](self._get_mp4_paths())
        elif isinstance(self._supported_formats['audio'][self.format], str):
            self.to_audio(self._get_mp4_paths(), self.format, self._supported_formats['audio'][self.format])
        else:
            self.end_with_msg(f'[!] Error: Output format must be one of {list(self.formats_summary)}')


    # Get mp4 files from input directory
    def _get_mp4_paths(self):
        # Check if output directory provided
        if self.output is None:
            self.output = self.input

        # Check if either input or output directory faulty
        for dir in [self.input, self.output]:
            if not os.path.exists(dir):
                self.end_with_msg(f'[!] Error: Directory {dir} does not exist.')

        print(f'Convert to {str(self.format).upper()} | Job started for {self.input}\n')

        file_paths = []

        # Get mp4 files from input dir; os.listdir() is explicitly not recursive
        for file in os.listdir(self.input):
            if file.lower().endswith('.mp4'):
                print(f'[+] Scheduling: {file}')
                file_paths.append(os.path.abspath(os.path.join(self.input, file)))

        # End if no mp4s found
        if len(file_paths) == 0:
            self.end_with_msg(f'[!] Warning: No mp4 files found in {self.input}')

        return file_paths


    # Convert mp4 to audio
    def to_audio(self, file_paths, output_format, codec):
        for file_path in file_paths:
            # Instantiate a video file clip for each mp4
            video = VideoFileClip(file_path, audio=True, fps_source='tbr')
            # Build output path
            output_path = os.path.abspath(os.path.join(self.output, str(os.path.basename(file_path)).lower().replace('.mp4', f'.{output_format}')))
            # Grab audio from video (AudioFileClip object)
            audio = video.audio
            
            # Check if audio was found
            if audio is None:
                print(f'[!] Warning: No audio found in "{file_path}" - Skipping\n')
                continue

            # Write audio to file
            audio.write_audiofile(output_path, codec=codec)
            audio.close()
            video.close()

            # Post process (delete mp4, print success)
            self._post_process(file_path, output_path, self.delete)


    # Convert mp4 to mp4 with different codec
    def to_codec(self, _, codec, file_paths):
        for file_path in file_paths:
            video = VideoFileClip(file_path, audio=True, fps_source='tbr')
            codec_mp4_path = os.path.abspath(os.path.join(self.output, str(os.path.basename(file_path)).lower().replace('.mp4', f'_{codec}.mp4')))
            # Write video with new codec and (customized or original) framerate
            video.write_videofile(codec_mp4_path, codec=codec, fps=video.fps if self.framerate is None else self.framerate, audio=True)
            video.close()
            self._post_process(file_path, codec_mp4_path, self.delete)


    # Convert mp4 to movie with different format
    def to_movie(self, format, codec, file_paths):
        for file_path in file_paths:
            video = VideoFileClip(file_path, audio=True, fps_source='tbr')
            out_path = os.path.abspath(os.path.join(self.output, str(os.path.basename(file_path)).lower().replace('.mp4', f'.{format}')))
            # File format is different, codec is file type specific, framerate is customized or original
            video.write_videofile(out_path, codec=codec, fps=video.fps if self.framerate is None else self.framerate, audio=True)
            video.close()
            self._post_process(file_path, out_path, self.delete)


    # Convert mp4 to frames as png
    def to_frames_png(self, file_paths):
        for file_path in file_paths:
            video = VideoFileClip(file_path, audio=False, fps_source='tbr')
            png_path = os.path.join(self.output, str(os.path.basename(file_path)).lower().replace('.mp4', ''))
            # Split video into individual png frame images at original framerate
            video.write_images_sequence(f"{png_path}-frame_%06d.png", fps=video.fps)
            video.close()
            self._post_process(file_path, png_path, self.delete)


    # Convert mp4 to gif
    def to_gif(self, file_paths):
        for file_path in file_paths:
            video = VideoFileClip(file_path, audio=False, fps_source='tbr')
            gif_path = os.path.join(self.output, str(os.path.basename(file_path)).lower().replace('.mp4', '.gif'))
            # Write gif with original framerate and all frames
            video.write_gif(gif_path, fps=video.fps)
            video.close()
            self._post_process(file_path, gif_path, self.delete)

    # Convert mp4 to frames in bmp format
    def to_bmp(self, file_paths):
        for file_path in file_paths:
            video = VideoFileClip(file_path, audio=False, fps_source='tbr')
            bmp_path = os.path.join(self.output, str(os.path.basename(file_path)).lower().replace('.mp4', ''))
            # Split video into individual bmp frame images at original framerate
            for i, frame in enumerate(video.iter_frames(fps=video.fps, dtype='uint8')):
                frame.save(f"{bmp_path}-frame_{i:06d}.bmp", format='bmp')
            self._post_process(file_path, bmp_path, self.delete)


    # Post process after (successful) conversion (delete mp4 if desired, print success)
    def _post_process(self, file_path, out_path, delete):
        print(f'[+] Converted "{file_path}" to "{out_path}"')
        if delete:
            os.remove(file_path)
            print(f'[-] Removed "{file_path}"')


# An object is interacted with through a CLI-interface
# In a minimal configuration, make sure at least 'input' and 'format' exist
if __name__ == '__main__':
    # Check if required libraries are installed
    for lib in ['moviepy']:
        try:
            __import__(lib)
        except ImportError as ie:
            print(f'Please install {lib}: {ie}')
            exit(1)

    mp4_to_any = Mp4ToAny()

    # Capture arguments from command line
    parser = argparse.ArgumentParser(description='Convert mp4 files to different media formats')
    parser.add_argument('-i', '--input', help='Directory containing mp4 files to be converted', type=str, required=False)
    parser.add_argument('-o', '--output', help='Directory to save files, writing to mp4 path if not provided', type=str, required=False)
    parser.add_argument('-f', '--format', help=f'Set the output format ({format(mp4_to_any.formats_summary)})', type=str, required=True)
    parser.add_argument('-fps', '--framerate', help='Set the output framerate (default: same as input)', type=int, required=False)
    parser.add_argument('-d', '--delete', help='Delete mp4 files after conversion', action='store_true', required=False)

    args = vars(parser.parse_args())

    # Run main function with parsed arguments
    mp4_to_any.convert(input=args['input'],
                       format=args['format'], 
                       output=args['output'], 
                       framerate=args['framerate'], 
                       delete=args['delete'])