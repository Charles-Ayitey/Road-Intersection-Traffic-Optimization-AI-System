"""
pack_for_colab.py
-----------------
Builds traffic_project.zip ready to upload to Google Colab.

What gets included:
  simulation/   — all SUMO network and route files
  data/         — every video (.mp4 .avi .mov .mkv .webm)
                  and image  (.jpg .jpeg .png .bmp) you have in data/
  colab_train.py — the self-contained Colab training script

All file paths inside the zip use forward slashes (Linux-safe)
even when run from Windows.

Usage:
    python pack_for_colab.py
Then upload traffic_project.zip to Colab and run:
    !unzip -q traffic_project.zip -d .
"""

import os
import zipfile

# ── Config ────────────────────────────────────────────────────
ROOT      = os.path.dirname(os.path.abspath(__file__))
OUTPUT    = os.path.join(ROOT, "traffic_project.zip")

VIDEO_EXT = {".mp4", ".avi", ".mov", ".mkv", ".webm"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp"}

# ── Helpers ───────────────────────────────────────────────────
def to_zip_path(abs_path):
    """Return a Linux-safe relative path for use inside the zip."""
    rel = os.path.relpath(abs_path, ROOT)
    return rel.replace("\\", "/")   # Windows backslash → forward slash


def collect_files():
    """Return a list of (abs_path, zip_path) tuples for everything to pack."""
    files = []

    # 1. simulation/ — all XML files
    sim_dir = os.path.join(ROOT, "simulation")
    if os.path.isdir(sim_dir):
        for fname in os.listdir(sim_dir):
            if fname.endswith(".xml") or fname.endswith(".sumocfg"):
                abs_path = os.path.join(sim_dir, fname)
                files.append((abs_path, to_zip_path(abs_path)))
    else:
        print(f"  WARNING: simulation/ folder not found at {sim_dir}")

    # 2. data/ — videos and images
    data_dir = os.path.join(ROOT, "data")
    if os.path.isdir(data_dir):
        for fname in sorted(os.listdir(data_dir)):
            ext = os.path.splitext(fname)[1].lower()
            if ext in VIDEO_EXT or ext in IMAGE_EXT:
                abs_path = os.path.join(data_dir, fname)
                files.append((abs_path, to_zip_path(abs_path)))
    else:
        print(f"  WARNING: data/ folder not found at {data_dir}")

    # 3. colab_train.py
    colab_script = os.path.join(ROOT, "colab_train.py")
    if os.path.exists(colab_script):
        files.append((colab_script, "colab_train.py"))
    else:
        print(f"  WARNING: colab_train.py not found — run this script from the project root")

    return files


# ── Main ──────────────────────────────────────────────────────
def main():
    print("Building traffic_project.zip for Google Colab...")
    print(f"  Project root : {ROOT}")
    print()

    files = collect_files()

    if not files:
        print("ERROR: No files found to pack. Check your project structure.")
        return

    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for abs_path, zip_path in files:
            size_kb = os.path.getsize(abs_path) / 1024
            print(f"  + {zip_path:<55}  ({size_kb:>8.1f} KB)")
            zf.write(abs_path, zip_path)

    total_kb = os.path.getsize(OUTPUT) / 1024
    print()
    print(f"Done!  {OUTPUT}")
    print(f"       {len(files)} files  |  {total_kb:.1f} KB compressed")
    print()
    print("Next steps:")
    print("  1. Upload traffic_project.zip to Google Colab")
    print("  2. In a Colab cell, run:")
    print("       !unzip -q traffic_project.zip -d .")
    print("  3. Run the Colab install commands at the top of colab_train.py")
    print("  4. Then run:  exec(open('colab_train.py').read())")
    print("  5. Download ppo_traffic_agent_refined.zip when training finishes")
    print("     and place it in your local models/ folder")


if __name__ == "__main__":
    main()
