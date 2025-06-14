import os
import argparse
import subprocess
import utils.language_support as lang
from core.controller import Controller

if __name__ == "__main__":
    # An object is interacted with through a CLI-interface
    # Check if required libraries are installed
    for lib in [
        "moviepy",
        "PIL",
        "flask",
        "flask_uploads",
        "docx",
        "pptx",
        "PyPDF2",
        "mammoth",
        "weasyprint",
        "markdownify",
    ]:
        try:
            __import__(lib)
        except ImportError as ie:
            print(f"Please install {lib}: {ie}")
            exit(1)

    controller = Controller()

    parser = argparse.ArgumentParser(
        description=f"{lang.get_translation('description', controller.locale)}",
    )
    parser.add_argument(
        "-i",
        "--input",
        nargs="+",
        help=f"{lang.get_translation('input_help', controller.locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-o",
        "--output",
        help=f"{lang.get_translation('output_help', controller.locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-f",
        "--format",
        help=f"{lang.get_translation('format_help', controller.locale)} ({', '.join(controller.supported_formats)})",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-m",
        "--merge",
        help=f"{lang.get_translation('merge_help', controller.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-c",
        "--concat",
        help=f"{lang.get_translation('concat_help', controller.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-fps",
        "--framerate",
        help=f"{lang.get_translation('framerate_help', controller.locale)}",
        type=int,
        required=False,
    )
    parser.add_argument(
        "-q",
        "--quality",
        help=f"{lang.get_translation('quality_help', controller.locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-d",
        "--delete",
        help=f"{lang.get_translation('delete_help', controller.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-w",
        "--web",
        help=f"{lang.get_translation('web_help', controller.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-a",
        "--across",
        help=f"{lang.get_translation('across_help', controller.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-r",
        "--recursive",
        help=f"{lang.get_translation('recursive_help', controller.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-z",
        "--dropzone",
        help=f"{lang.get_translation('dropzone_help', controller.locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-l",
        "--language",
        help=f"{lang.get_translation('locale_help', controller.locale)}",
        type=str,
        required=False,
    )

    args = vars(parser.parse_args())

    if args["language"] in lang.LANGUAGE_CODES.keys():
        # Reinitialize controller with new language
        controller = Controller(locale=lang.LANGUAGE_CODES[args["language"]])

    if args["web"]:
        # Check for web frontend request
        if os.name in ["nt"]:
            subprocess.run("python ./web_to_any.py", shell=True)
        else:
            subprocess.run("python3 ./web_to_any.py", shell=True)
    else:
        # Run main function with parsed arguments
        controller.run(
            input_path_args=args["input"],
            format=args["format"],
            output=args["output"],
            framerate=args["framerate"],
            quality=args["quality"],
            merge=args["merge"],
            concat=args["concat"],
            delete=args["delete"],
            across=args["across"],
            recursive=args["recursive"],
            dropzone=args["dropzone"],
            language=args["language"],
        )
