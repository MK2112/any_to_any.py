import os
import sys
import shutil
import platform
import PyInstaller.__main__
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Use upx for compression if available (can be installed on Linux with `sudo apt install upx` or on Windows with a binary download)

def clean_build():
    for dir_name in ['build', 'dist']:
        if os.path.exists(dir_name):
            print(f"Removing {dir_name} directory...")
            shutil.rmtree(dir_name)

def build_executable():
    print("Building executable with PyInstaller...")
    common_args = [
        '--name=AnyToAnyConverter',
        '--onefile',
        '--windowed',                               # Don't show console for GUI app
        '--noconfirm',                              # Overwrite output directory without confirmation
        '--clean',                                  # Clean PyInstaller cache
        '--exclude-module=_tkinter',                # Exclude tkinter
        '--exclude-module=matplotlib.tests',
        '--exclude-module=numpy.random._examples',
        '--exclude-module=scipy',                   # Exclude scipy if not needed
        '--exclude-module=torch.distributed',       # Exclude distributed training
        '--exclude-module=torch.testing',
        '--exclude-module=torchvision.models',      # Exclude pre-trained models
        '--exclude-module=torchaudio',              # Exclude audio processing if not needed
        '--exclude-module=sklearn',                 # Exclude scikit-learn if not needed
        '--exclude-module=skimage',                 # Exclude scikit-image if not needed
        '--exclude-module=PIL._tkinter_finder',
        '--strip'                                   # Strip debug symbols
    ]
    
    # Add compression
    # Enable UPX compression if UPX is installed
    common_args.extend(['--upx-dir', ''])
    
    # Add data files
    common_args.extend([
        '--add-data=assets:assets',
        '--add-data=templates:templates',
        '--add-data=utils:utils',
        '--add-data=core:core',
    ])
    
    # Add hidden imports
    common_args.extend([
        '--hidden-import=PyQt6',
        '--hidden-import=PIL',
        '--hidden-import=moviepy',
        '--hidden-import=docx',
        '--hidden-import=pptx',
        '--hidden-import=PyPDF2',
        '--hidden-import=mammoth',
        '--hidden-import=weasyprint',
        '--hidden-import=markdownify',
        '--hidden-import=fitz',
        '--hidden-import=PyMuPDF',
    ])
    
    try:
        from pathlib import Path
        plugins_path = Path('/home/MK2112/venvs/ai/lib/python3.12/site-packages/PyQt6/Qt6/plugins')
        plugin_dirs = ['platforms', 'imageformats']
        if platform.system() == 'Windows':
            for plugin_dir in plugin_dirs:
                if (plugins_path / plugin_dir).exists():
                    common_args.append(f'--add-binary={plugins_path}/{plugin_dir}/*;{plugin_dir}/')
        elif platform.system() == 'Darwin':
            for plugin_dir in plugin_dirs:
                if (plugins_path / plugin_dir).exists():
                    common_args.append(f'--add-binary={plugins_path}/{plugin_dir}/*;Contents/MacOS/{plugin_dir}/')
            common_args.append('--osx-bundle-identifier=com.anytoany.converter')
        else:
            for plugin_dir in plugin_dirs:
                if (plugins_path / plugin_dir).exists():
                    common_args.append(f'--add-binary={plugins_path}/{plugin_dir}/*:{plugin_dir}')
    except Exception as e:
        print(f"Warning: Could not find PyQt6 plugins: {e}")
        print("The application might not work correctly without the plugins.")
    
    common_args.append('gui/qt_app.py')
    os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    common_args.extend([
        '--hidden-import=PyQt6.QtCore',
        '--hidden-import=PyQt6.QtGui',
        '--hidden-import=PyQt6.QtWidgets',
        '--hidden-import=PyQt6.QtNetwork',
    ])
    
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
