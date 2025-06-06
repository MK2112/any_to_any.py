import os
from PIL import Image
from moviepy import VideoFileClip
from utils.category import Category


def gif_to_frames(output: str, file_paths: dict, file_handler) -> None:
    # Convert GIFs to frames, place those in a folder
    gifs = [
        image_path
        for image_path in file_paths[Category.IMAGE]
        if image_path[2] == "gif"
    ]
    if len(gifs) > 0:
        for image_path_set in gifs:
            clip = VideoFileClip(file_handler.join_back(image_path_set), audio=False)
            # Calculate zero-padding width based on total number of frames
            total_frames = int(clip.duration * clip.fps)
            num_digits = len(str(total_frames))
            # Create a dedicated folder for the gif to store its frames
            if not os.path.exists(os.path.join(output, image_path_set[1])):
                os.makedirs(os.path.join(output, image_path_set[1]), exist_ok=True)
            for i, frame in enumerate(clip.iter_frames(fps=clip.fps, dtype="uint8")):
                frame_filename = f"{image_path_set[1]}-{i:0{num_digits}d}.png"
                frame_path = os.path.abspath(
                    os.path.join(output, image_path_set[1], frame_filename)
                )
                Image.fromarray(frame).save(frame_path, format="PNG")
            clip.close()
