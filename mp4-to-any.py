import os
import argparse
from moviepy.editor import VideoFileClip
"""
Taking an input directory of mp4 files, convert them to a multitude of formats using moviepy.
Interact with the script using the command line arguments defined at the bottom of this file.
"""

def _get_mp4_paths(args):
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


def to_audio(args, mp4_paths, output_format, codec):
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
        _post_process(mp4_path, output_path, args['delete'])


def to_codec(args, _, codec, mp4_paths):
    for mp4_path in mp4_paths:
        video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
        codec_mp4_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', f'_{codec}.mp4')))
        video.write_videofile(codec_mp4_path, codec=codec, fps=video.fps if args['framerate'] is None else args['framerate'], audio=True)
        video.close()
        _post_process(mp4_path, codec_mp4_path, args['delete'])


def to_movie(args, format, codec, mp4_paths):
    for mp4_path in mp4_paths:
        video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
        out_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', f'.{format}')))
        video.write_videofile(out_path, codec=codec, fps=video.fps if args['framerate'] is None else args['framerate'], audio=True)
        video.close()
        _post_process(mp4_path, out_path, args['delete'])


def to_frames_png(args, mp4_paths):
    for mp4_path in mp4_paths:
        video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
        png_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', ''))
        video.write_images_sequence(f"{png_path}-frame_%06d.png", fps=video.fps) # Write every frame as png
        video.close()
        _post_process(mp4_path, png_path, args['delete'])


def to_gif(args, mp4_paths):
    for mp4_path in mp4_paths:
        video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
        gif_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '.gif'))
        video.write_gif(gif_path, fps=video.fps) # Combine all frames to gif
        video.close()
        _post_process(mp4_path, gif_path, args['delete'])


def to_bmp(args, mp4_paths):
    for mp4_path in mp4_paths:
        video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
        bmp_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', ''))
        for i, frame in enumerate(video.iter_frames(fps=video.fps, dtype='uint8')):
            frame.save(f"{bmp_path}-frame_{i:06d}.bmp", format='bmp')
        _post_process(mp4_path, bmp_path, args['delete'])


def _post_process(mp4_path, out_path, delete):
    print(f'[+] Converted "{mp4_path}" to "{out_path}"')

    if delete:
        os.remove(mp4_path)
        print(f'[-] Removed "{mp4_path}"')


_supported_formats = {
        'mp3': 'libmp3lame',
        'flac': 'flac',
        'ogg': 'libvorbis',
        'wav': 'pcm_s16le',
        'gif': to_gif,
        'png': to_frames_png,
        'bmp': to_bmp,
        'webm': (to_movie, 'libvpx'),
        'mov': (to_movie, 'libx264'),
        'mkv': (to_movie, 'libx264'),
        'h265': (to_codec, 'libx265'),
        'h264': (to_codec, 'libx264'),
        'xvid': (to_codec, 'libxvid'),
        'mpeg4': (to_codec, 'mpeg4'),
        'avi': (to_movie, 'libx264'),
    }


def main(args):
    # Check if supported format was specified
    if args['format'] in _supported_formats:
        if isinstance(_supported_formats[args['format']], tuple):
            _supported_formats[args['format']][0](args, args['format'], _supported_formats[args['format']][1], _get_mp4_paths(args))
        elif isinstance(_supported_formats[args['format']], str):
            to_audio(args, _get_mp4_paths(args), args['format'], _supported_formats[args['format']])
        else:
            _supported_formats[args['format']](args, _get_mp4_paths(args))
    else:
        print(f'[!] Error: Output format must be one of {list(_supported_formats.keys())}')
        exit(1)


if __name__ == '__main__':
    # Check if required libraries are installed
    for lib in ['moviepy']:
        try:
            __import__(lib)
        except ImportError as ie:
            print(f'Please install {lib}: {ie}')
            exit(1)

    # Capture arguments from command line
    parser = argparse.ArgumentParser(description='Convert mp4 files to mp3')
    parser.add_argument('-i', '--input', help='Directory containing mp4 files to be converted', type=str, required=True)
    parser.add_argument('-o', '--output', help='Directory to save mp3 files, writing to mp4 path if not provided', type=str, required=False)
    parser.add_argument('-f', '--format', help=f'Set the output format ({format(_supported_formats.keys())})', type=str, required=True)
    parser.add_argument('-fps', '--framerate', help='Set the output framerate (default: same as input)', type=int, required=False)
    parser.add_argument('-d', '--delete', help='Delete mp4 files after conversion', action='store_true', required=False)

    # Run main function with parsed arguments
    main(vars(parser.parse_args()))
