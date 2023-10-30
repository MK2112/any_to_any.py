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
            'mp3': 'libmp3lame',
            'flac': 'flac',
            'ogg': 'libvorbis',
            'wav': 'pcm_s16le',
            'gif': self.to_gif,
            'png': self.to_frames_png,
            'bmp': self.to_bmp,
            'webm': (self.to_movie, 'libvpx'),
            'mov': (self.to_movie, 'libx264'),
            'mkv': (self.to_movie, 'libx264'),
            'h265': (self.to_codec, 'libx265'),
            'h264': (self.to_codec, 'libx264'),
            'xvid': (self.to_codec, 'libxvid'),
            'mpeg4': (self.to_codec, 'mpeg4'),
            'avi': (self.to_movie, 'libx264'),
        }


    # Getter for formats to convert to; Useful for CLI interface
    def supported_formats(self):
        return self._supported_formats.keys()


    # Single point of exit for the script
    def end_with_msg(self, msg):
        print(msg)
        exit(1)


    # Main function to convert mp4 files to defined formats
    def convert(self, input, format, output, framerate, delete):
        self.input = input
        self.format = format
        self.output = output
        self.framerate = framerate
        self.delete = delete
        
        # Check if specified format is supported
        if self.format in self._supported_formats:
            # Check if value associated to format is tuple/string or function to call specific conversion
            if isinstance(self._supported_formats[self.format], tuple):
                self._supported_formats[self.format][0](self.format, self._supported_formats[self.format][1], self._get_mp4_paths())
            elif isinstance(self._supported_formats[self.format], str):
                self.to_audio(self._get_mp4_paths(), self.format, self._supported_formats[self.format])
            else:
                self._supported_formats[self.format](self._get_mp4_paths())
        else:
            self.end_with_msg(f'[!] Error: Output format must be one of {list(self._supported_formats.keys())}')


    # Get all mp4 files from input directory
    def _get_mp4_paths(self):
        # Check if output directory provided
        if self.output is None:
            self.output = self.input

        # Check if either input or output directory faulty
        for dir in [self.input, self.output]:
            if not os.path.exists(dir):
                self.end_with_msg(f'[!] Error: Directory {dir} does not exist.')

        print(f'MP4->{str(self.format).upper()} | Job started for {self.input}\n')

        mp4_paths = []

        # Get mp4 files from input dir; os.listdir() is explicitly not recursive
        for file in os.listdir(self.input):
            if file.lower().endswith('.mp4'):
                print(f'[+] Scheduling: {file}')
                mp4_paths.append(os.path.abspath(os.path.join(self.input, file)))

        # End if no mp4s found
        if len(mp4_paths) == 0:
            self.end_with_msg(f'[!] Warning: No mp4 files found in {self.input}')

        return mp4_paths


    # Convert mp4 to audio
    def to_audio(self, mp4_paths, output_format, codec):
        for mp4_path in mp4_paths:
            # Instantiate a video file clip for each mp4
            video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
            # Build output path
            output_path = os.path.abspath(os.path.join(self.output, str(os.path.basename(mp4_path)).lower().replace('.mp4', f'.{output_format}')))
            # Grab audio from video (AudioFileClip object)
            audio = video.audio
            
            # Check if audio was found
            if audio is None:
                print(f'[!] Warning: No audio found in "{mp4_path}" - Skipping\n')
                continue

            # Write audio to file
            audio.write_audiofile(output_path, codec=codec)
            audio.close()
            video.close()

            # Post process (delete mp4, print success)
            self._post_process(mp4_path, output_path, self.delete)


    # Convert mp4 to mp4 with different codec
    def to_codec(self, _, codec, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
            codec_mp4_path = os.path.abspath(os.path.join(self.output, str(os.path.basename(mp4_path)).lower().replace('.mp4', f'_{codec}.mp4')))
            # Write video with new codec and (customized or original) framerate
            video.write_videofile(codec_mp4_path, codec=codec, fps=video.fps if self.framerate is None else self.framerate, audio=True)
            video.close()
            self._post_process(mp4_path, codec_mp4_path, self.delete)


    # Convert mp4 to movie with different format
    def to_movie(self, format, codec, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
            out_path = os.path.abspath(os.path.join(self.output, str(os.path.basename(mp4_path)).lower().replace('.mp4', f'.{format}')))
            # File format is different, codec is file type specific, framerate is customized or original
            video.write_videofile(out_path, codec=codec, fps=video.fps if self.framerate is None else self.framerate, audio=True)
            video.close()
            self._post_process(mp4_path, out_path, self.delete)


    # Convert mp4 to frames as png
    def to_frames_png(self, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
            png_path = os.path.join(self.output, str(os.path.basename(mp4_path)).lower().replace('.mp4', ''))
            # Split video into individual png frame images at original framerate
            video.write_images_sequence(f"{png_path}-frame_%06d.png", fps=video.fps)
            video.close()
            self._post_process(mp4_path, png_path, self.delete)


    # Convert mp4 to gif
    def to_gif(self, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
            gif_path = os.path.join(self.output, str(os.path.basename(mp4_path)).lower().replace('.mp4', '.gif'))
            # Write gif with original framerate and all frames
            video.write_gif(gif_path, fps=video.fps)
            video.close()
            self._post_process(mp4_path, gif_path, self.delete)

    # Convert mp4 to frames in bmp format
    def to_bmp(self, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
            bmp_path = os.path.join(self.output, str(os.path.basename(mp4_path)).lower().replace('.mp4', ''))
            # Split video into individual bmp frame images at original framerate
            for i, frame in enumerate(video.iter_frames(fps=video.fps, dtype='uint8')):
                frame.save(f"{bmp_path}-frame_{i:06d}.bmp", format='bmp')
            self._post_process(mp4_path, bmp_path, self.delete)


    # Post process after (successful) conversion (delete mp4 if desired, print success)
    def _post_process(self, mp4_path, out_path, delete):
        print(f'[+] Converted "{mp4_path}" to "{out_path}"')
        if delete:
            os.remove(mp4_path)
            print(f'[-] Removed "{mp4_path}"')


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
    parser = argparse.ArgumentParser(description='Convert mp4 files to mp3')
    parser.add_argument('-i', '--input', help='Directory containing mp4 files to be converted', type=str, required=True)
    parser.add_argument('-o', '--output', help='Directory to save mp3 files, writing to mp4 path if not provided', type=str, required=False)
    parser.add_argument('-f', '--format', help=f'Set the output format ({format(mp4_to_any.supported_formats())})', type=str, required=True)
    parser.add_argument('-fps', '--framerate', help='Set the output framerate (default: same as input)', type=int, required=False)
    parser.add_argument('-d', '--delete', help='Delete mp4 files after conversion', action='store_true', required=False)

    args = vars(parser.parse_args())

    # Run main function with parsed arguments
    mp4_to_any.convert(input=args['input'], 
                       format=args['format'], 
                       output=args['output'], 
                       framerate=args['framerate'], 
                       delete=args['delete'])