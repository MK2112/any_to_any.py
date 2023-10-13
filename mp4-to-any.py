import os
import argparse
from moviepy.editor import VideoFileClip
from moviepy.video.io.ffmpeg_tools import ffmpeg_extract_audio


def main(args):

    # These output formats are supported    
    if args['format'] == 'mp3':
        mp4_to_mp3(args)
    elif args['format'] == 'gif':
        mp4_to_gif(args)
    elif args['format'] == 'png':
        mp4_to_frames_png(args)
    else:
        print(f'[!] Error: Output format must be one of {["mp3", "gif", "png"]}')
        exit(1)


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
            print(f'Scheduling: {file}')
            mp4_paths.append(os.path.abspath(os.path.join(args['input'], file)))

    if len(mp4_paths) == 0:
        print(f'[!] Warning: No mp4 files found in {args["input"]}')
        exit(1)


def mp4_to_mp3(args):
    # Check if input and output directories exist
    mp4_paths = _get_mp4_paths(args)

    for mp4_path in mp4_paths:
        try:
            # Obtain absolute paths for mp4 and mp3 files
            # Combine args['output'] and mp4_path's basename
            mp3_path = os.path.abspath(os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '.mp3')))

            # Initialize video with audio and specific time base reference
            video = VideoFileClip(mp4_path, audio=True, fps_source='tbr')
            audio = video.audio

            # Write audio as mp3
            audio.write_audiofile(mp3_path)

            # Close audio and video files
            audio.close()
            video.close()

            print(f'[+] Converted "{mp4_path}" to "{mp3_path}"')

            if args['delete']:
                os.remove(mp4_path)
                print(f'[-] Removed "{mp4_path}"')
            print()
        
        # Trying a workaround for if access rights seem obstructing
        except KeyError as ke:
            try:
                ffmpeg_extract_audio(mp4_path, mp3_path)
                print(f'[+] Converted "{mp4_path}" to "{mp3_path}"')
                if args['delete']:
                    os.remove(mp4_path)
                    print(f'[-] Removed "{mp4_path}"')
                print()
                continue                
            except PermissionError as pe:
                print(pe)
                continue


def mp4_to_frames_png(args):
    mp4_paths = _get_mp4_paths(args)

    for mp4_path in mp4_paths:
        png_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', ''))
        clip = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
        clip.write_images_sequence(f"{png_path}-frame_%04d.png", fps=clip.fps) # Write every frame as png
        clip.close()

        print(f'[+] Converted "{mp4_path}" to "{png_path}"')

        if args['delete']:
            os.remove(mp4_path)
            print(f'[-] Removed "{mp4_path}"')
        print()


def mp4_to_gif(args):
    mp4_paths = _get_mp4_paths(args)

    for mp4_path in mp4_paths:
        gif_path = os.path.join(args['output'], str(os.path.basename(mp4_path)).lower().replace('.mp4', '.gif'))
        
        clip = VideoFileClip(mp4_path, audio=False, fps_source='tbr')
        clip.write_gif(gif_path, fps=clip.fps) # Write every frame as gif

        print(f'[+] Converted "{mp4_path}" to "{gif_path}"')

        if args['delete']:
            os.remove(mp4_path)
            print(f'[-] Removed "{mp4_path}"')
        print()


if __name__ == '__main__':
    # Check if moviepy is installed
    try:
        import moviepy
    except ImportError as ie:
        print(f'Please install moviepy: {ie}')
        exit(1)

    # Capture arguments from command line
    parser = argparse.ArgumentParser(description='Convert mp4 files to mp3')
    parser.add_argument('-i','--input', help='Directory containing mp4 files to be converted', required=True)
    parser.add_argument('-o','--output', help='Directory to save mp3 files, writing to mp4 path if not provided', required=False)
    parser.add_argument('-f','--format', help='Set the output format (mp3/gif/png)', required=True)
    parser.add_argument('-d','--delete', help='Delete mp4 files after conversion', action='store_true', required=False)

    main(vars(parser.parse_args()))
