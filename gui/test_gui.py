import sys
import os
import platform
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

def test_pyqt6_import():
    import importlib.util
    if importlib.util.find_spec('PyQt6') is not None:
        return True
    else:
        print("Please PyQt6 install it with: pip install -r requirements-gui.txt")
        return False

def test_gui_import():
    import importlib.util
    if importlib.util.find_spec('gui.qt_app') is None:
        print("[!] GUI module not found")
        return False
    try:
        from gui.qt_app import MainWindow
        return True
    except ImportError as e:
        print(f"[!] Failed to import GUI application: {e}")
        return False
    except Exception as e:
        print(f"[!] Error during GUI import: {e}")
        return False

def test_gui_launch():
    print("Testing GUI application launch...")
    print(f"Python version: {platform.python_version()}")
    print(f"Platform: {platform.system()} {platform.release()}")
    try:
        # Checking dependencies
        if not test_pyqt6_import():
            return False
        # Try to import the main application
        if not test_gui_import():
            return False
        print("\nAll GUI tests passed!")
        return True
    except Exception as e:
        print(f"[!] Error during test: {e}")
        return False

def main():
    success = test_gui_launch()
    if success:
        print("\n[>] GUI application should be ready to use!")
        print("You can now run: python qt_app.py")
    return 0 if success else 1

if __name__ == "__main__":
    sys.exit(main())
