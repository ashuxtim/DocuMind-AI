import os

# 1. Define the extensions you want to capture
EXTENSIONS = {'.py', '.js', '.jsx', '.css'}

# 2. Define folders to strictly ignore (prevents massive files)
IGNORE_DIRS = {'node_modules', '.git', '__pycache__', 'venv', 'env', 'dist', 'build', '.next'}

OUTPUT_FILE = 'documind_full_code.txt'

def merge_files():
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as outfile:
        # Walk through all folders recursively
        for root, dirs, files in os.walk('.'):
            # Modify 'dirs' in-place to skip ignored folders so we don't even enter them
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            for file in files:
                if any(file.endswith(ext) for ext in EXTENSIONS):
                    file_path = os.path.join(root, file)
                    
                    # Create a clear divider
                    divider = f"\n\n{'='*60}\nFILE: {file_path}\n{'='*60}\n"
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as infile:
                            content = infile.read()
                            outfile.write(divider)
                            outfile.write(content)
                            print(f"Added: {file_path}")
                    except Exception as e:
                        print(f"Skipped {file_path} due to error: {e}")

if __name__ == "__main__":
    print("Starting code merge...")
    merge_files()
    print(f"\nDone! All code is in: {OUTPUT_FILE}")