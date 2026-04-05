import os
import sys
import shutil
import platform
import tempfile
import PyInstaller.__main__

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

##
# Use UPX for compression
##
# Linux: sudo apt install upx-ucl
# Windows: choco install upx
##


def clean_build():
    for dir_name in ["build", "dist"]:
        if os.path.exists(dir_name):
            print(f"Removing {dir_name} directory...")
            shutil.rmtree(dir_name)


def _prepare_windows_icon(repo_root: str) -> str | None:
    # Find icon image for pyinstaller
    candidates = [
        os.path.join(repo_root, "img", "app_icon.ico"),
        os.path.join(repo_root, "img", "app_icon.png"),
        os.path.join(repo_root, "img", "icon.ico"),
        os.path.join(repo_root, "img", "icon.png"),
        os.path.join(repo_root, "app_icon.ico"),
        os.path.join(repo_root, "app_icon.png"),
    ]

    source_icon = next((p for p in candidates if os.path.exists(p)), None)
    if not source_icon:
        print("No app icon provided. Using default executable icon.")
        return None

    if source_icon.lower().endswith(".ico"):
        print(f"Using Windows .ico icon: {source_icon}")
        return source_icon

    # PNG -> ICO for Windows
    try:
        from PIL import Image

        tmp_dir = os.path.join(tempfile.gettempdir(), "any_to_any_build")
        os.makedirs(tmp_dir, exist_ok=True)
        out_ico = os.path.join(tmp_dir, "app_icon.ico")

        with Image.open(source_icon) as img:
            if img.mode != "RGBA":
                img = img.convert("RGBA")
            img.save(
                out_ico,
                format="ICO",
                sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
            )

        print(f"Converted icon for Windows executable: {source_icon} -> {out_ico}")
        return out_ico
    except Exception as e:
        print(f"Warning: Could not prepare Windows icon from '{source_icon}': {e}")
        return None


def build_executable():
    print("Building executable with PyInstaller...")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_root)
    path_sep = os.pathsep
    common_args = [
        "--name=AnyToAny",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--exclude-module=_tkinter",
        "--exclude-module=matplotlib.tests",
        "--exclude-module=numpy.random._examples",
        "--exclude-module=scipy",
        "--exclude-module=PIL._tkinter_finder",
    ]

    if platform.system() == "Windows":
        common_args.extend(["--onefile", "--noupx"])
        icon_path = _prepare_windows_icon(repo_root)
        if icon_path:
            common_args.append(f"--icon={icon_path}")
        print("UPX disabled on Windows to avoid python DLL load failures.")
    else:
        common_args.extend(["--onefile", "--strip"])
        upx_path = shutil.which("upx")
        if not upx_path:
            raise RuntimeError("UPX not found on PATH. Install UPX before building.")
        common_args.extend(["--upx-dir", os.path.dirname(upx_path)])

    for data_dir in ["assets", "templates", "utils", "core"]:
        data_path = os.path.join(repo_root, data_dir)
        if os.path.exists(data_path):
            common_args.append(f"--add-data={data_path}{path_sep}{data_dir}")
        else:
            print(f"Warning: Data directory not found, skipping: {data_path}")

    common_args.extend(
        [
            "--hidden-import=PyQt6",
            "--hidden-import=PIL",
            "--hidden-import=moviepy",
            "--collect-all=numpy",
            "--collect-all=imageio",
            "--collect-all=imageio_ffmpeg",
            "--hidden-import=docx",
            "--hidden-import=pptx",
            "--hidden-import=pypdf",
            "--hidden-import=mammoth",
            "--collect-all=reportlab",
            "--hidden-import=markdownify",
            "--hidden-import=fitz",
            "--hidden-import=PyMuPDF",
        ]
    )

    if platform.system() != "Windows":
        common_args.extend(
            [
                "--hidden-import=weasyprint",
                "--collect-all=weasyprint",
                "--collect-all=cffi",
            ]
        )

    try:
        from pathlib import Path
        from PyQt6.QtCore import QLibraryInfo

        plugins_path = Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath))
        plugin_dirs = ["platforms", "imageformats"]

        if platform.system() == "Windows":
            for plugin_dir in plugin_dirs:
                if (plugins_path / plugin_dir).exists():
                    common_args.append(
                        f"--add-binary={plugins_path / plugin_dir}/*{path_sep}{plugin_dir}/"
                    )
        else:
            for plugin_dir in plugin_dirs:
                if (plugins_path / plugin_dir).exists():
                    common_args.append(
                        f"--add-binary={plugins_path / plugin_dir}/*{path_sep}{plugin_dir}"
                    )
    except Exception as e:
        print(f"Warning: Could not find PyQt6 plugins: {e}")
        print("The application might not work correctly without the plugins.")

    common_args.append("gui/qt_app.py")
    common_args.extend(
        [
            "--hidden-import=PyQt6.QtCore",
            "--hidden-import=PyQt6.QtGui",
            "--hidden-import=PyQt6.QtWidgets",
            "--hidden-import=PyQt6.QtNetwork",
        ]
    )

    PyInstaller.__main__.run(common_args)


def main():
    clean_build()
    build_executable()
    print("\n[>] Build completed successfully!")
    print(f"Executable located in: {os.path.abspath('dist')}")


if __name__ == "__main__":
    sys.exit(main())
