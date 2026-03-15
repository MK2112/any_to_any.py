import os
import sys
import shutil
import platform
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


def build_executable():
    print("Building executable with PyInstaller...")
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    os.chdir(repo_root)
    path_sep = os.pathsep
    common_args = [
        "--name=AnyToAnyConverter",
        "--windowed",  # Don't show console for GUI app
        "--noconfirm",  # Overwrite output directory without confirmation
        "--clean",  # Clean PyInstaller cache
        "--exclude-module=_tkinter",  # Exclude tkinter
        "--exclude-module=matplotlib.tests",
        "--exclude-module=numpy.random._examples",
        "--exclude-module=scipy",  # Exclude scipy if not needed
        "--exclude-module=torch.distributed",  # Exclude distributed training
        "--exclude-module=torch.testing",
        "--exclude-module=torchvision.models",  # Exclude pre-trained models
        "--exclude-module=torchaudio",  # Exclude audio processing if not needed
        "--exclude-module=sklearn",  # Exclude scikit-learn if not needed
        "--exclude-module=skimage",  # Exclude scikit-image if not needed
        "--exclude-module=PIL._tkinter_finder",
    ]

    # Use onefile everywhere; avoid Windows-only UPX/strip issues
    if platform.system() == "Windows":
        common_args.extend(["--onefile", "--noupx"])
    else:
        common_args.extend(["--onefile", "--strip"])

    # Enable UPX compression (skip on Windows due to DLL load issues)
    if platform.system() == "Windows":
        print("UPX disabled on Windows to avoid python DLL load failures.")
    else:
        upx_path = shutil.which("upx")
        if not upx_path:
            raise RuntimeError("UPX not found on PATH. Install UPX before building.")
        common_args.extend(["--upx-dir", os.path.dirname(upx_path)])

    # Add data files when present
    data_dirs = ["assets", "templates", "utils", "core"]
    for data_dir in data_dirs:
        data_path = os.path.join(repo_root, data_dir)
        if os.path.exists(data_path):
            common_args.append(f"--add-data={data_path}{path_sep}{data_dir}")
        else:
            print(f"Warning: Data directory not found, skipping: {data_path}")

    # Add hidden imports
    common_args.extend(
        [
            "--hidden-import=PyQt6",
            "--hidden-import=PIL",
            "--hidden-import=moviepy",
            "--collect-all=imageio",
            "--collect-all=imageio_ffmpeg",
            "--hidden-import=docx",
            "--hidden-import=pptx",
            "--hidden-import=pypdf",
            "--hidden-import=mammoth",
            "--hidden-import=weasyprint",
            "--hidden-import=markdownify",
            "--hidden-import=fitz",
            "--hidden-import=PyMuPDF",
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
        elif platform.system() == "Darwin":
            for plugin_dir in plugin_dirs:
                if (plugins_path / plugin_dir).exists():
                    common_args.append(
                        f"--add-binary={plugins_path / plugin_dir}/*{path_sep}Contents/MacOS/{plugin_dir}/"
                    )
            common_args.append("--osx-bundle-identifier=com.anytoany.converter")
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
    # Make sure PyInstaller is available
    clean_build()
    build_executable()
    print("\n[>] Build completed successfully!")
    print(f"Executable located in: {os.path.abspath('dist')}")


if __name__ == "__main__":
    import sys

    sys.exit(main())
