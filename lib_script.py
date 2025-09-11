import os
import re

def extract_version_from_file(file_path):
    """
    Try to extract __version__ or VERSION string from a .py file.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if "__version__" in line or "VERSION" in line.upper():
                    match = re.search(r'["\']([\d\.]+)["\']', line)
                    if match:
                        return match.group(1)
    except Exception:
        return None
    return None

def generate_circuitpython_library_list(lib_folder="lib"):
    """
    Generates a list of CircuitPython libraries and their versions (if found).
    """
    if not os.path.exists(lib_folder):
        print(f"Error: '{lib_folder}' not found.")
        return

    libraries = {}

    for item in os.listdir(lib_folder):
        item_path = os.path.join(lib_folder, item)

        if os.path.isdir(item_path) and not item.startswith('.'):
            # Look for version.py or __init__.py
            version = None
            for candidate in ["version.py", "__init__.py", f"{item}.py"]:
                candidate_path = os.path.join(item_path, candidate)
                if os.path.exists(candidate_path):
                    version = extract_version_from_file(candidate_path)
                    if version:
                        break
            libraries[item] = version or "unknown"

        elif os.path.isfile(item_path) and (item.endswith(".py") or item.endswith(".mpy")):
            lib_name = os.path.splitext(item)[0]
            version = extract_version_from_file(item_path)
            libraries[lib_name] = version or "unknown"

    with open("circuitpython_libraries.txt", "w") as f:
        f.write("# CircuitPython Libraries used in this project\n")
        for lib, ver in sorted(libraries.items()):
            f.write(f"{lib} (version: {ver})\n")

    print("Generated circuitpython_libraries.txt")

if __name__ == "__main__":
    generate_circuitpython_library_list()
