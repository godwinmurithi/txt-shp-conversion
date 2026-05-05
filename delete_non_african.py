"""
delete_non_african.py
=====================
Deletes all non-African country subfolders from your geonames directory,
freeing up space before the rename/flatten step.

  Before:
    geonames/  KE/  UG/  TZ/  US/  DE/  JP/  CN/  ...

  After:
    geonames/  KE/  UG/  TZ/  (only African countries remain)

Usage
-----
  python delete_non_african.py
  python delete_non_african.py --geonames-dir "C:/Users/Admin/Documents/geonames"
  python delete_non_african.py --dry-run      # preview what WOULD be deleted, safe to run first
"""

import os
import sys
import shutil
import argparse

# ── 58 African country codes (ISO 3166-1 alpha-2) ────────────────────────────
AFRICAN_COUNTRIES = {
    "DZ", "AO", "BJ", "BW", "BF", "BI", "CM", "CV", "CF", "TD",
    "KM", "CD", "CG", "CI", "DJ", "EG", "GQ", "ER", "ET", "GA",
    "GM", "GH", "GN", "GW", "KE", "LS", "LR", "LY", "MG", "MW",
    "ML", "MR", "MU", "YT", "MA", "MZ", "NA", "NE", "NG", "RE",
    "RW", "SH", "ST", "SN", "SC", "SL", "SO", "ZA", "SS", "SD",
    "SZ", "TZ", "TG", "TN", "UG", "EH", "ZM", "ZW",
}


def delete_non_african(geonames_dir: str, dry_run: bool = False):
    geonames_dir = os.path.abspath(geonames_dir)

    if not os.path.isdir(geonames_dir):
        print(f"[ERROR] Folder not found: {geonames_dir}")
        sys.exit(1)

    # Find all 2-letter subfolders that are NOT African
    all_subfolders = [
        f for f in os.listdir(geonames_dir)
        if os.path.isdir(os.path.join(geonames_dir, f))
        and len(f) == 2
        and f.upper() not in AFRICAN_COUNTRIES
    ]

    to_delete = sorted(all_subfolders)

    if not to_delete:
        print("[INFO] Nothing to delete — only African country folders found.")
        return

    # Calculate total size to be freed
    def folder_size(path):
        total = 0
        for dirpath, _, files in os.walk(path):
            for f in files:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    pass
        return total

    total_bytes = sum(folder_size(os.path.join(geonames_dir, f)) for f in to_delete)
    total_mb    = total_bytes / (1024 * 1024)

    mode = "DRY RUN — nothing will be deleted" if dry_run else "LIVE RUN"

    print(f"\n{'='*62}")
    print(f"  Delete Non-African Country Folders  [{mode}]")
    print(f"  Folder  : {geonames_dir}")
    print(f"  To delete: {len(to_delete)} folders  (~{total_mb:.1f} MB freed)")
    print(f"{'='*62}\n")

    if not dry_run:
        # Safety confirmation
        print("  Folders to be PERMANENTLY deleted:")
        for cc in to_delete:
            print(f"    {cc}/")
        print()
        confirm = input(f"  Type YES to confirm deletion of {len(to_delete)} folders: ").strip()
        if confirm != "YES":
            print("\n[CANCELLED] Nothing was deleted.")
            return
        print()

    deleted = 0
    skipped = 0

    for cc in to_delete:
        folder_path = os.path.join(geonames_dir, cc)
        size_mb     = folder_size(folder_path) / (1024 * 1024)

        if dry_run:
            print(f"  [DRY RUN] Would delete: {cc}/  ({size_mb:.1f} MB)")
            deleted += 1
        else:
            try:
                shutil.rmtree(folder_path)
                print(f"  ✓ Deleted: {cc}/  ({size_mb:.1f} MB)")
                deleted += 1
            except Exception as e:
                print(f"  ✗ Error deleting {cc}/: {e}")
                skipped += 1

    action = "Would free" if dry_run else "Freed"
    print(f"\n{'='*62}")
    print(f"  {action}   : ~{total_mb:.1f} MB")
    print(f"  Deleted  : {deleted}  |  Errors: {skipped}")
    print(f"{'='*62}\n")

    if dry_run:
        print("  Run without --dry-run to actually delete.\n")


def main():
    parser = argparse.ArgumentParser(
        description="Delete all non-African country folders from your geonames directory."
    )
    parser.add_argument(
        "--geonames-dir", "-d",
        default=r"C:\Users\Admin\Documents\geonames",
        help="Path to your geonames folder (default: C:\\Users\\Admin\\Documents\\geonames)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without actually deleting anything.",
    )
    args = parser.parse_args()

    delete_non_african(
        geonames_dir=args.geonames_dir,
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
