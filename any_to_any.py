import os
import argparse
import subprocess
import utils.language_support as lang
from core.controller import Controller

####
## Any_to_Any.py Entry Script
## Refer to README.md for more information and usage examples
####

if __name__ == "__main__":
    # Interactable with through:
    # - a CLI-interface,
    # - a web interface, or
    # - an application using this as its backend.
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
    parser.add_argument(
        "-s",
        "--split",
        help=f"{lang.get_translation('split_help', controller.locale)}",
        type=str,
        required=False,
    )
    parser.add_argument(
        "--workers",
        help="Maximum worker threads to use for per-file conversions (default: 1)",
        type=int,
        default=1,
        required=False,
    )

    args = vars(parser.parse_args())

    if args["language"] in lang.LANGUAGE_CODES.keys():
        # Reinitialize controller with new language
        controller = Controller(locale=lang.LANGUAGE_CODES[args["language"]])

    if args["split"] and (args["merge"] or args["concat"]):
        parser.error(
            f"{lang.get_translation('split_merge_error', controller.locale)}"
        )

    if args["merge"] and args["concat"]:
        parser.error(
            f"{lang.get_translation('merge_concat_error', controller.locale)}"
        )
    
    if args["web"]:
        # Windows wants this expressed differently
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
            split=args["split"],
            merge=args["merge"],
            concat=args["concat"],
            delete=args["delete"],
            across=args["across"],
            recursive=args["recursive"],
            dropzone=args["dropzone"],
            language=args["language"],
            workers=args["workers"],
        )
