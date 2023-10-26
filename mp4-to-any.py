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


    def supported_formats(self):
        return self._supported_formats.keys()


    def convert(self, args):
        # Check if supported format was specified
        if args['format'] in self._supported_formats:
            if isinstance(self._supported_formats[args['format']], tuple):
                self._supported_formats[args['format']][0](args, args['format'], self._supported_formats[args['format']][1], self._get_mp4_paths(args))
            elif isinstance(self._supported_formats[args['format']], str):
                self.to_audio(args, self._get_mp4_paths(args), args['format'], self._supported_formats[args['format']])
            else:
                self._supported_formats[args['format']](args, self._get_mp4_paths(args))
        else:
            print(f'[!] Error: Output format must be one of {list(self._supported_formats.keys())}')
            exit(1)


    def _get_mp4_paths(self, args):
        # Check if output directory provided
        if args['output'] is None:
            args['output'] = args['input']

        # Check if either input or output directory faulty
        for dir in [args['input'], args['output']]:
            if not os.path.exists(dir):
                print(f'[!] Error: Directory {dir} does not exist.')
                exit(1)

        print(f'MP4->{str(args["format"]).upper()} | Job started for {args["input"]}\n')

        mp4_paths = []

        # Get mp4 files from input dir
        for file in os.listdir(args['input']):
            if file.lower().endswith('.mp4'):
                print(f'[+] Scheduling: {file}')
                mp4_paths.append(os.path.abspath(os.path.join(args['input'], file)))

        # Gracefully exit if no mp4s found
        if len(mp4_paths) == 0:
            print(f'[!] Warning: No mp4 files found in {args["input"]}')
            exit(1)

        return mp4_paths


    def to_audio(self, args, mp4_paths, output_format, codec):
        for mp4_path in mp4_paths:
            # Instantiate a video file clip for each mp4
            video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
            # Build output path
            output_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', f'.{output_format}')))
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
            self._post_process(mp4_path, output_path, args['delete'])


    def to_codec(self, args, _, codec, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
            codec_mp4_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', f'_{codec}.mp4')))
            video.write_videofile(codec_mp4_path, codec=codec, fps=video.fps if args['framerate'] is None else args['framerate'], audio=True)
            video.close()
            self._post_process(mp4_path, codec_mp4_path, args['delete'])


    def to_movie(self, args, format, codec, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
            out_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', f'.{format}')))
            video.write_videofile(out_path, codec=codec, fps=video.fps if args['framerate'] is None else args['framerate'], audio=True)
            video.close()
            self._post_process(mp4_path, out_path, args['delete'])


    def to_frames_png(self, args, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
            png_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', ''))
            video.write_images_sequence(f"{png_path}-frame_%06d.png", fps=video.fps) # Write every frame as png
            video.close()
            self._post_process(mp4_path, png_path, args['delete'])


    def to_gif(self, args, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
            gif_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '.gif'))
            video.write_gif(gif_path, fps=video.fps) # Combine all frames to gif
            video.close()
            self._post_process(mp4_path, gif_path, args['delete'])


    def to_bmp(self, args, mp4_paths):
        for mp4_path in mp4_paths:
            video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
            bmp_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', ''))
            for i, frame in enumerate(video.iter_frames(fps=video.fps, dtype='uint8')):
                frame.save(f"{bmp_path}-frame_{i:06d}.bmp", format='bmp')
            self._post_process(mp4_path, bmp_path, args['delete'])


    def _post_process(self, mp4_path, out_path, delete):
        print(f'[+] Converted "{mp4_path}" to "{out_path}"')

        if delete:
            os.remove(mp4_path)
            print(f'[-] Removed "{mp4_path}"')


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

    # Run main function with parsed arguments
    mp4_to_any.convert(vars(parser.parse_args()))