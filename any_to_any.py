import os
import argparse
import subprocess
from moviepy.editor import *
from PIL import Image


class AnyToAny:
    """
    Taking an input directory of mp4 files, convert them to a multitude of formats using moviepy.
    Interact with the script using the command line arguments defined at the bottom of this file.
    """

    def __init__(self):

        # Setting up a dictionary of supported formats 
        # and respective information
        self._supported_formats = {
            'audio': {
                'mp3':  'libmp3lame',
                'flac': 'flac',
                'ogg':  'libvorbis',
                'wav':  'pcm_s16le',
                'm4a':  'aac',
            },
            'image': {
                'gif': self.to_gif,
                'png': self.to_frames_png,
                'bmp': self.to_bmp,
                'webp': self.to_webp,
            },
            'movie': {
                'webm': 'libvpx',
                'mov':  'libx264',
                'mkv':  'libx264',
                'avi':  'libx264',
                'mp4':  'libx264',
            },
            'movie_codecs': {
                'av1':   'libaom-av1',
                'vp9':   'libvpx-vp9',
                'h265':  'libx265',
                'h264':  'libx264',
                'xvid':  'libxvid',
                'mpeg4': 'mpeg4',
            },
        }

        # This is used in the CLI information output
        self.supported_formats = [format for formats in self._supported_formats.values() for format in formats.keys()]
    

    # Single point of exit for the script
    def end_with_msg(self, msg):
        print(msg)
        exit(1)

    
    # Return bitrate for audio conversion
    def _audio_bitrate(self, format, quality):
        # If formats allow for a higher bitrate, we shift our scale accordingly
        if format in ['flac', 'wav']:
            return {
                'high': '500k',
                'medium': '320k',
                'low': '192k'
            }.get(quality, None)
        else:
            return {
                'high': '320k',
                'medium': '192k',
                'low': '128k'
            }.get(quality, None)


    # Main function to convert media files to defined formats
    def convert(self, input, format, output, framerate, quality, delete):
        self.input = input if input is not None else os.getcwd() # No input means working directory
        self.format = format.lower() if format is not None else None
        self.output = output if output is not None else self.input # No output means same as input
        self.framerate = framerate
        self.delete = delete

        if quality is not None:
            self.quality = quality.lower() if quality.lower() in ['high', 'medium', 'low'] else None
        else:
            self.quality = None

        # Check if value associated to format is tuple/string or function to call specific conversion
        if self.format in self._supported_formats['movie'].keys():
            self.to_movie(file_paths=self._get_file_paths(), format=self.format, codec=self._supported_formats['movie'][self.format])
        elif self.format in self._supported_formats['audio'].keys():
            self.to_audio(file_paths=self._get_file_paths(), format=self.format, codec=self._supported_formats['audio'][self.format])
        elif self.format in self._supported_formats['movie_codecs'].keys():
            self.to_codec(file_paths=self._get_file_paths(), codec=self._supported_formats['movie_codecs'][self.format])
        elif self.format in self._supported_formats['image'].keys():
            self._supported_formats['image'][self.format](self._get_file_paths())
        else:
            # Handle unsupported formats here
            self.end_with_msg(f'[!] Error: Output format must be one of {list(self.supported_formats)}')

        print("\n[+] Job Finished")


    # Get media files from input directory
    def _get_file_paths(self):
        if self.output is None:
            self.output = self.input

        # Sanity check for existence of input and output directories
        for dir in [self.input, self.output]:
            if not os.path.exists(dir):
                self.end_with_msg(f'[!] Error: Directory {dir} Does Not Exist.')

        print(f'Convert To {str(self.format).upper()} | Job Started For {self.input}\n')

        # Discover and immediately attribute files to their specific category
        categories = self._supported_formats.keys()
        file_paths = {category: [] for category in categories}

        for file in os.listdir(self.input):
            file = os.path.abspath(os.path.join(self.input, file)) # Get absolute path to file
            file_ending = file[file.rfind('.')+1:].lower()         # Get file ending (e.g. mp4)
            file_name = file[file.rfind(os.sep)+1:file.rfind('.')] # Get file name (e.g. video)
            path_to_file = file[:file.rfind(os.sep)+1]             # Get path to file (e.g. /home/user/)

            found = False

            for category in categories:
                # Check if file ending is supported for any category
                if file_ending in self._supported_formats[category].keys():
                    file_paths[category].append([path_to_file, file_name, file_ending])
                    print(f'[+] Scheduling: {file_name}.{file_ending}')
                    found = True
                    break

            if not found:
                # Handle files with unsupported formats here
                print(f'[!] Skipping {file_name}.{file_ending} - Unsupported Format')
                continue

        # Check if any files were found
        if len(file_paths['audio']) == 0 and len(file_paths['image']) == 0 and len(file_paths['movie']) == 0:
            self.end_with_msg(f'[!] Warning: No Convertable Media Files Found In {self.input}')

        # A dictionary of lists of file paths, one list per file category, it being the key
        return file_paths


    # Convert to audio
    def to_audio(self, file_paths, format, codec):
        # Audio to audio conversion
        for audio_path_set in file_paths['audio']:
            audio = AudioFileClip(self._join_back(audio_path_set))
            if audio_path_set[2] != format:
                output_path = os.path.abspath(os.path.join(self.output, f'{audio_path_set[1]}.{format}'))
                # Write audio to file
                audio.write_audiofile(output_path, codec=codec, bitrate=self._audio_bitrate(format, self.quality))
                audio.close()
                self._post_process(audio_path_set, output_path, self.delete)
            else:   
                print(f'[!] Skipping "{self._join_back(audio_path_set)}"\n')

        # Movie to audio conversion
        for movie_path_set in file_paths['movie']:
            video = VideoFileClip(self._join_back(movie_path_set), audio=True, fps_source='tbr')
            output_path = os.path.abspath(os.path.join(self.output, f'{movie_path_set[1]}.{format}'))
            audio = video.audio
            # Check if audio was found
            if audio is None:
                print(f'[!] No audio found in "{self._join_back(movie_path_set)}" - Skipping\n')
                continue
            # Write audio to file
            audio.write_audiofile(output_path, codec=codec, bitrate=self._audio_bitrate(format, self.quality))
            audio.close()
            video.close()
            # Post process (delete mp4, print success)
            self._post_process(movie_path_set, output_path, self.delete)


    # Convert movie to same movie with different codec
    def to_codec(self, file_paths, codec):
        for codec_path_set in file_paths['movie']: # Jup, this is on purpose
            video = VideoFileClip(self._join_back(codec_path_set), audio=True, fps_source='tbr')
            output_path = os.path.abspath(os.path.join(self.output, f'{codec_path_set[1]}_{codec}.{codec_path_set[2]}'))
            video.write_videofile(output_path, codec=codec, fps=video.fps if self.framerate is None else self.framerate, audio=True)
            video.close()
            self._post_process(codec_path_set, output_path, self.delete)


    # Convert to movie with specified format
    def to_movie(self, file_paths, format, codec):
        pngs = bmps = []
        # Images (gif, png, bmp)
        for image_path_set in file_paths['image']:
            # Depending on the format, different fragmentation is required
            if image_path_set[2].lower() == 'gif':
                clip = ImageSequenceClip(self._join_back(image_path_set), fps=24)
                out_path = os.path.abspath(os.path.join(self.output, f'{image_path_set[1]}.{format}'))
                clip.write_videofile(out_path, codec=codec, fps=clip.fps if self.framerate is None else self.framerate, audio=True)
                clip.close()
                self._post_process(image_path_set, out_path, self.delete)
            elif image_path_set[2].lower() == 'png':
                pngs.append(ImageClip(self._join_back(image_path_set)).set_duration(1))
            elif image_path_set[2].lower() == 'bmp':
                bmps.append(ImageClip(self._join_back(image_path_set)).set_duration(1))

        # PNG to movie
        if len(pngs) > 0:
            final_clip = concatenate_videoclips(pngs, method="compose")
            out_path = os.path.abspath(os.path.join(self.output, f'png_merged.{format}'))
            final_clip.write_videofile(out_path, fps=24 if self.framerate is None else self.framerate, codec=codec)
            final_clip.close()

        # BMP to movie
        if len(bmps) > 0:
            final_clip = concatenate_videoclips(bmps, method="compose")
            out_path = os.path.abspath(os.path.join(self.output, f'bmp_merged.{format}'))
            final_clip.write_videofile(out_path, fps=24 if self.framerate is None else self.framerate, codec=codec)
            final_clip.close()
            
        # Movie ... to other movie
        for movie_path_set in file_paths['movie']:
            if not movie_path_set[2].lower() == format:
                video = VideoFileClip(self._join_back(movie_path_set), audio=True, fps_source='tbr')
                out_path = os.path.abspath(os.path.join(self.output, f'{movie_path_set[1]}.{format}'))
                video.write_videofile(out_path, codec=codec, fps=video.fps if self.framerate is None else self.framerate, audio=True)
                video.close()
                self._post_process(movie_path_set, out_path, self.delete)


    # Converting to image frame sets
    # This works for images and movies only
    def to_frames_png(self, file_paths):
        for image_path_set in file_paths['image']:
            # We only need to care for gif and bmp, rather obvisouly
            if image_path_set[2].lower() == 'gif':
                clip = ImageSequenceClip(self._join_back(image_path_set), fps=24)
                for _, frame in enumerate(clip.iter_frames(fps=clip.fps, dtype='uint8')):
                    frame_path = os.path.abspath(os.path.join(self.output, f'{image_path_set[1]}-%06d.png'))
                    Image.fromarray(frame).save(frame_path, format='png')
                clip.close()
                self._post_process(image_path_set, self.output, self.delete)
            elif image_path_set[2].lower() == 'bmp':
                png_path = os.path.abspath(os.path.join(self.output, f'{image_path_set[1]}.png'))
                with Image.open(self._join_back(image_path_set)) as img:
                    img.convert("RGB").save(png_path, format='png')
                self._post_process(image_path_set, png_path, self.delete)
        
        # Audio cant be image-framed, but movies certrainly can
        for movie_path_set in file_paths['movie']:
            video = VideoFileClip(self._join_back(movie_path_set), audio=False, fps_source='tbr')
            if not os.path.exists(os.path.join(self.output, movie_path_set[1])):
                os.makedirs(os.path.join(self.output, movie_path_set[1]))
            png_path = os.path.abspath(os.path.join(os.path.join(self.output, movie_path_set[1]), f'{movie_path_set[1]}-%06d.png'))
            video.write_images_sequence(png_path, fps=video.fps)
            video.close()
            self._post_process(movie_path_set, png_path, self.delete)


    # Convert to gif
    def to_gif(self, file_paths):
        # For now, all images in the input directory are merged into one gif
        if len(file_paths['image']) > 0:
            images = []
            for image_path_set in file_paths['image']:
                with Image.open(self._join_back(image_path_set)) as image:
                    images.append(image.convert('RGBA'))
            images[0].save(os.path.join(self.output, 'merged.gif'), save_all=True, append_images=images[1:])
        
        # Movies are converted to gifs as well, incorporating all frames
        for movie_path_set in file_paths['movie']:
            video = VideoFileClip(self._join_back(movie_path_set), audio=False, fps_source='tbr')
            gif_path = os.path.join(self.output, f'{movie_path_set[1]}.gif')
            video.write_gif(gif_path, fps=video.fps)
            video.close()
            self._post_process(movie_path_set, gif_path, self.delete)


    # Convert frames in bmp format
    def to_bmp(self, file_paths):
        # Movies are converted to bmps, frame by frame
        for movie_path_set in file_paths['movie']:
            video = VideoFileClip(self._join_back(movie_path_set), audio=False, fps_source='tbr')
            bmp_path = os.path.join(self.output, f'{movie_path_set[1]}.bmp')
            # Split video into individual bmp frame images at original framerate
            for _, frame in enumerate(video.iter_frames(fps=video.fps, dtype='uint8')):
                frame.save(f"{bmp_path}-%06d.bmp", format='bmp')
            self._post_process(movie_path_set, bmp_path, self.delete)

        # Pngs and gifs are converted to bmps as well
        for image_path_set in file_paths['images']:
            if not image_path_set[2].lower() == 'bmp':
                if image_path_set[2].lower() == 'png':
                    bmp_path = os.path.join(self.output, f'{image_path_set[1]}.bmp')
                    with Image.open(self._join_back(image_path_set)) as img:
                        img.convert("RGB").save(bmp_path, format='BMP')
                elif image_path_set[2].lower() == 'gif':
                    clip = VideoFileClip(self._join_back(image_path_set))
                    for _, frame in enumerate(clip.iter_frames(fps=clip.fps, dtype='uint8')):
                        frame_path = os.path.join(self.output, f"{image_path_set[1]}-%06d.bmp")
                        Image.fromarray(frame).convert("RGB").save(frame_path, format='BMP')
                else:
                    # Handle unsupported file types here
                    print(f"[!] Skipping {self._join_back(image_path_set)} - Unsupported format")
    
    
    # Convert frames in webp format
    def to_webp(self, file_paths):
        # Movies are converted to webps, frame by frame
        for movie_path_set in file_paths['movie']:
            video = VideoFileClip(self._join_back(movie_path_set), audio=False, fps_source='tbr')
            webp_path = os.path.join(self.output, f'{movie_path_set[1]}.webp')
            # Split video into individual webp frame images at original framerate
            for _, frame in enumerate(video.iter_frames(fps=video.fps, dtype='uint8')):
                frame.save(f"{webp_path}-%06d.webp", format='webp')
            self._post_process(movie_path_set, webp_path, self.delete)

        # Pngs and gifs are converted to webps as well
        for image_path_set in file_paths['images']:
            if not image_path_set[2].lower() == 'webp':
                if image_path_set[2].lower() == 'png':
                    webp_path = os.path.join(self.output, f'{image_path_set[1]}.webp')
                    with Image.open(self._join_back(image_path_set)) as img:
                        img.convert("RGB").save(webp_path, format='webp')
                elif image_path_set[2].lower() == 'gif':
                    clip = VideoFileClip(self._join_back(image_path_set))
                    for _, frame in enumerate(clip.iter_frames(fps=clip.fps, dtype='uint8')):
                        frame_path = os.path.join(self.output, f"{image_path_set[1]}-%06d.webp")
                        Image.fromarray(frame).convert("RGB").save(frame_path, format='webp')
                else:
                    # Handle unsupported file types here
                    print(f"[!] Skipping {self._join_back(image_path_set)} - Unsupported format")


    # Post process after conversion, print, delete source file if desired
    def _post_process(self, file_path_set, out_path, delete):
        print(f'[+] Converted "{self._join_back(file_path_set)}" to "{out_path}"')
        if delete:
            os.remove(self._join_back(file_path_set))
            print(f'[-] Removed "{file_path_set}"')


    # Join back the file path set to a concurrent path
    def _join_back(self, file_path_set):
        return os.path.abspath(f'{file_path_set[0]}{file_path_set[1]}.{file_path_set[2]}')


# An object is interacted with through a CLI-interface
# In a minimal configuration, make sure at least 'input' and 'format' exist
if __name__ == '__main__':
    # Check if required libraries are installed
    for lib in ['moviepy', 'PIL']:
        try:
            __import__(lib)
        except ImportError as ie:
            print(f'Please install {lib}: {ie}')
            exit(1)

    any_to_any = AnyToAny()

    # Capture arguments from command line
    parser = argparse.ArgumentParser(description='Convert media files to different media formats')
    parser.add_argument('-i', '--input', help='Directory containing media files to be converted, Working Directory if none provided', type=str, required=False)
    parser.add_argument('-o', '--output', help='Directory to save files, writing to mp4 path if not provided', type=str, required=False)
    parser.add_argument('-f', '--format', help=f'Set the output format ({any_to_any.supported_formats})', type=str, required=False)
    parser.add_argument('-fps', '--framerate', help='Set the output framerate (default: same as input)', type=int, required=False)
    parser.add_argument('-q', '--quality', help='Set the output quality (high/medium/low)', type=str, required=False)
    parser.add_argument('-d', '--delete', help='Delete mp4 files after conversion', action='store_true', required=False)
    parser.add_argument('-w', '--web', help='Ignores all other arguments, starts web server + frontend', action='store_true', required=False)

    args = vars(parser.parse_args())

    # Check if web frontend is desired
    if args['web']:
        subprocess.run("python ./web_to_any.py")
    else:
        # Run main function with parsed arguments
        any_to_any.convert(input=args['input'],
                           format=args['format'], 
                           output=args['output'], 
                           framerate=args['framerate'],
                           quality=args['quality'], 
                           delete=args['delete'])