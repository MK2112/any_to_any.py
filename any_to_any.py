import argparse
from core.cli import run_cli
from core.web import run_web
from core.formats import get_supported_formats
from lang.translations import get_system_language, get_translation

if __name__ == "__main__":
    # Check if required libraries are installed
    for lib in ["moviepy", "PIL"]:
        try:
            __import__(lib)
        except ImportError as ie:
            print(f"Please install {lib}: {ie}")
            exit(1)

    locale = get_system_language()

    parser = argparse.ArgumentParser(
        description=f"{get_translation('description', locale)}",
    )
    parser.add_argument(
        "-i",
        "--input",
        nargs="+",
        help=f"{get_translation('input_help', locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-o",
        "--output",
        help=f"{get_translation('output_help', locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-f",
        "--format",
        help=f"{get_translation('format_help', locale)} ({', '.join(get_supported_formats())})",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-m",
        "--merge",
        help=f"{get_translation('merge_help', locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-c",
        "--concat",
        help=f"{get_translation('concat_help', locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-fps",
        "--framerate",
        help=f"{get_translation('framerate_help', locale)}",
        type=int,
        required=False,
    )
    parser.add_argument(
        "-q",
        "--quality",
        help=f"{get_translation('quality_help', locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "-d",
        "--delete",
        help=f"{get_translation('delete_help', locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-w",
        "--web",
        help=f"{get_translation('web_help', locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-a",
        "--across",
        help=f"{get_translation('across_help', locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-r",
        "--recursive",
        help=f"{get_translation('recursive_help', locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-z",
        "--dropzone",
        help=f"{get_translation('dropzone_help', locale)}",
        action="store_true",
        required=False,
    )
    parser.add_argument(
        "-l",
        "--language",
        help=f"{get_translation('locale_help', locale)}",
        type=str,
        required=False,
    )

    args = vars(parser.parse_args())

    if args["web"]:
        run_web()
    else:
        run_cli(
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
