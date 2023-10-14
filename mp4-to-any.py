import os
import argparse
from moviepy.editor import VideoFileClip


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

    for file in os.listdir(args['input']):
        if file.lower().endswith('.mp4'):
            print(f'[+] Scheduling: {file}')
            mp4_paths.append(os.path.abspath(os.path.join(args['input'], file)))

    if len(mp4_paths) == 0:
        print(f'[!] Warning: No mp4 files found in {args["input"]}')
        exit(1)

    return mp4_paths


def to_mp3(args, mp4_paths):
    for mp4_path in mp4_paths:
        # Obtain absolute paths for mp4 and mp3 files
        # Combine args['output'] and mp4_path's basename
        mp3_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '.mp3')))

        # Initialize video with audio and specific time base reference
        video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
        audio = video.audio

        if audio is None:
            print(f'[!] Warning: No audio found in "{mp4_path}" - Skipping\n')
            continue

        # Write audio to mp3 file
        audio.write_audiofile(mp3_path)
        
        # Close video and audio file handles
        audio.close()
        video.close()

        # Post-flight dialogue for this file
        _post_process(mp4_path, mp3_path, args['delete'])


def to_webm(args, mp4_paths):
    for mp4_path in mp4_paths:
        webm_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '.webm')))
        video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
        video.write_videofile(webm_path, codec="libvpx", fps=video.fps, audio=True)
        video.close()
        _post_process(mp4_path, webm_path, args['delete'])


def to_frames_png(args, mp4_paths):
    for mp4_path in mp4_paths:
        png_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', ''))
        video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
        video.write_images_sequence(f"{png_path}-frame_%06d.png", fps=video.fps) # Write every frame as png
        video.close()
        _post_process(mp4_path, png_path, args['delete'])


def to_gif(args, mp4_paths):
    for mp4_path in mp4_paths:
        gif_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '.gif'))
        video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
        video.write_gif(gif_path, fps=video.fps) # Write every frame as gif
        video.close()
        _post_process(mp4_path, gif_path, args['delete'])


def to_bmp(args, mp4_paths):
    for mp4_path in mp4_paths:
        bmp_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', ''))
        video = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
        for i, frame in enumerate(video.iter_frames(fps=video.fps, dtype='uint8')):
            frame.save(f"{bmp_path}-frame_{i:06d}.bmp", format='bmp')
        _post_process(mp4_path, bmp_path, args['delete'])


def to_flac(args, mp4_paths):
    for mp4_path in mp4_paths:
        flac_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '.flac')))
        video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
        audio = video.audio

        if audio is None:
            print(f'[!] Warning: No audio found in "{mp4_path}" - Skipping\n')
            continue

        audio.write_audiofile(flac_path, codec='flac')
        audio.close()
        video.close()
        _post_process(mp4_path, flac_path, args['delete'])


def to_h265(args, mp4_paths):
    for mp4_path in mp4_paths:
        h265_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '_h265.mp4')))
        video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
        video.write_videofile(h265_path, codec="libx265", fps=video.fps, audio=True)
        video.close()
        _post_process(mp4_path, h265_path, args['delete'])


def to_avi(args, mp4_paths):
    for mp4_path in mp4_paths:
        avi_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '.avi')))
        video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
        video.write_videofile(avi_path, codec="libx264", fps=video.fps, audio=True)
        video.close()
        _post_process(mp4_path, avi_path, args['delete'])


def _post_process(mp4_path, out_path, delete):
    print(f'[+] Converted "{mp4_path}" to "{out_path}"')

    if delete:
        os.remove(mp4_path)
        print(f'[-] Removed "{mp4_path}"')


_supported_formats = {
        'mp3': to_mp3,
        'gif': to_gif,
        'png': to_frames_png,
        'webm': to_webm,
        'flac': to_flac,
        'h265': to_h265,
        'avi': to_avi,
        'bmp': to_bmp,
    }


def main(args):
    # Check if supported format was specified
    if args['format'] in _supported_formats:
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
    parser.add_argument('-i','--input', help='Directory containing mp4 files to be converted', required=True)
    parser.add_argument('-o','--output', help='Directory to save mp3 files, writing to mp4 path if not provided', required=False)
    parser.add_argument('-f','--format', help=f'Set the output format ({format(_supported_formats.keys())})', required=True)
    parser.add_argument('-d','--delete', help='Delete mp4 files after conversion', action='store_true', required=False)

    main(vars(parser.parse_args()))
