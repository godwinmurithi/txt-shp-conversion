"""
geonames_download_and_convert.py
=================================
One script that does everything:
  1. Scrapes https://download.geonames.org/export/dump/ for all country zips
  2. Downloads them into  Downloads/geonames/zips/
  3. Converts each one to a point shapefile in  Downloads/geonames/<CC>/<CC>.shp

Downloads/
└── geonames/
    ├── zips/          ← raw downloaded zips (kept so you can re-run without re-downloading)
    │   ├── KE.zip
    │   ├── UG.zip
    │   └── ...
    ├── KE/
    │   ├── KE.shp
    │   ├── KE.dbf
    │   ├── KE.prj
    │   ├── KE.shx
    │   └── KE.cpg
    ├── UG/
    │   └── UG.shp ...
    └── ...

Usage
-----
  python geonames_download_and_convert.py                        # all countries
  python geonames_download_and_convert.py --only KE UG TZ       # specific countries
  python geonames_download_and_convert.py --skip-download        # convert already-downloaded zips
  python geonames_download_and_convert.py --workers 4            # parallel downloads (default: 4)

QGIS Python Console
-------------------
  exec(open(r"C:/Users/YourName/Downloads/geonames_download_and_convert.py").read())

Requirements
------------
  pip install geopandas pandas shapely fiona pyproj requests
"""

import os
import re
import sys
import time
import zipfile
import tempfile
import argparse
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests
import pandas as pd
import geopandas as gpd

# ── Config ────────────────────────────────────────────────────────────────────
BASE_URL    = "https://download.geonames.org/export/dump/"
CHUNK_SIZE  = 1024 * 256   # 256 KB download chunks

# GeoNames column spec (tab-delimited, no header)
COLUMNS = [
    "geonameid", "name", "asciiname", "alternatenames",
    "latitude", "longitude",
    "feature_class", "feature_code",
    "country_code", "cc2",
    "admin1_code", "admin2_code", "admin3_code", "admin4_code",
    "population", "elevation", "dem",
    "timezone", "modification_date",
]

# Output columns (DBF field names must be ≤ 10 chars)
KEEP_COLUMNS = [
    "geonameid", "name", "asciiname",
    "latitude", "longitude",
    "feat_class", "feat_code",
    "country", "admin1", "admin2",
    "population", "elevation",
    "timezone", "mod_date",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_downloads_folder() -> str:
    if os.name == "nt":
        import ctypes, ctypes.wintypes
        buf = ctypes.create_unicode_buffer(ctypes.wintypes.MAX_PATH)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x0005, None, 0, buf)
        path = buf.value
        if path:
            return path
    return os.path.join(os.path.expanduser("~"), "Downloads")


def scrape_country_codes() -> list[str]:
    """Fetch the GeoNames dump index and return only 2-letter country code zips.

    Explicitly excludes all non-country bulk files:
      allCountries, alternateNames, alternateNamesV2, cities*, adminCode5,
      hierarchy, no-country, shapes_*, userTags
    """
    # These are known non-country zips on the dump page — never download them
    EXCLUDE = {
        "allCountries", "alternateNames", "alternateNamesV2",
        "cities500", "cities1000", "cities5000", "cities15000",
        "adminCode5", "hierarchy", "no-country",
        "shapes_all_low", "shapes_simplified_lo", "userTags",
    }

    print(f"[INFO] Fetching index: {BASE_URL}")
    r = requests.get(BASE_URL, timeout=30)
    r.raise_for_status()

    # Match ONLY standalone 2-uppercase-letter filenames (ISO country codes)
    # Negative lookbehind/ahead ensures we never match inside longer filenames
    codes = re.findall(r'(?<![A-Za-z])([A-Z]{2})\.zip(?![A-Za-z])', r.text)
    codes = sorted(
        cc for cc in set(codes)
        if cc not in EXCLUDE          # belt-and-suspenders: skip any accidental match
    )

    print(f"[INFO] Found {len(codes)} country zips (bulk files excluded)")
    return codes


def human_size(path: str) -> str:
    size = os.path.getsize(path)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


# ── Download one zip ──────────────────────────────────────────────────────────

def download_zip(cc: str, zips_dir: str, force: bool = False) -> dict:
    url      = f"{BASE_URL}{cc}.zip"
    out_path = os.path.join(zips_dir, f"{cc}.zip")
    result   = {"cc": cc, "status": None, "size": "", "error": ""}

    if os.path.isfile(out_path) and not force:
        result["status"] = "CACHED"
        result["size"]   = human_size(out_path)
        return result

    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(out_path, "wb") as f:
            for chunk in r.iter_content(CHUNK_SIZE):
                if chunk:
                    f.write(chunk)
        result["status"] = "DOWNLOADED"
        result["size"]   = human_size(out_path)
    except Exception as e:
        result["status"] = "ERROR"
        result["error"]  = str(e)

    return result


# ── Convert one zip to shapefile ──────────────────────────────────────────────

def convert_zip(cc: str, zips_dir: str, output_dir: str) -> dict:
    zip_path      = os.path.join(zips_dir, f"{cc}.zip")
    country_folder = os.path.join(output_dir, cc)
    out_shp       = os.path.join(country_folder, f"{cc}.shp")
    result        = {"cc": cc, "status": None, "features": 0, "error": ""}

    if not os.path.isfile(zip_path):
        result["status"] = "SKIP"
        result["error"]  = "Zip not found"
        return result

    try:
        os.makedirs(country_folder, exist_ok=True)

        with zipfile.ZipFile(zip_path, "r") as zf:
            # Find the country txt inside the zip
            txt_files = [
                f for f in zf.namelist()
                if f.lower().endswith(".txt")
                and os.path.splitext(os.path.basename(f))[0].upper() == cc
            ]
            if not txt_files:
                txt_files = [
                    f for f in zf.namelist()
                    if f.lower().endswith(".txt") and "readme" not in f.lower()
                ]
            if not txt_files:
                result["status"] = "SKIP"
                result["error"]  = "No .txt found in zip"
                return result

            with tempfile.TemporaryDirectory() as tmp:
                zf.extract(txt_files[0], tmp)
                txt_path = os.path.join(tmp, txt_files[0])

                df = pd.read_csv(
                    txt_path,
                    sep="\t",
                    header=None,
                    names=COLUMNS,
                    dtype=str,
                    encoding="utf-8",
                    na_filter=False,
                    on_bad_lines="warn",
                    low_memory=False,
                )

        df["latitude"]   = pd.to_numeric(df["latitude"],   errors="coerce")
        df["longitude"]  = pd.to_numeric(df["longitude"],  errors="coerce")
        df["population"] = pd.to_numeric(df["population"], errors="coerce").fillna(0).astype(int)
        df["elevation"]  = pd.to_numeric(df["elevation"],  errors="coerce")
        df = df.dropna(subset=["latitude", "longitude"])

        df = df.rename(columns={
            "feature_class":     "feat_class",
            "feature_code":      "feat_code",
            "country_code":      "country",
            "admin1_code":       "admin1",
            "admin2_code":       "admin2",
            "modification_date": "mod_date",
        })
        df = df[[c for c in KEEP_COLUMNS if c in df.columns]].copy()

        gdf = gpd.GeoDataFrame(
            df,
            geometry=gpd.points_from_xy(df["longitude"], df["latitude"]),
            crs="EPSG:4326",
        )
        gdf.to_file(out_shp, encoding="utf-8")

        result["status"]   = "OK"
        result["features"] = len(gdf)

    except Exception:
        result["status"] = "ERROR"
        result["error"]  = traceback.format_exc(limit=3)

    return result


# ── Main pipeline ─────────────────────────────────────────────────────────────

def run(
    downloads_folder: str = None,
    only: list[str] = None,
    skip_download: bool = False,
    workers: int = 4,
    force_redownload: bool = False,
):
    if downloads_folder is None:
        downloads_folder = get_downloads_folder()

    geonames_dir = os.path.join(downloads_folder, "geonames")
    zips_dir     = os.path.join(geonames_dir, "zips")
    os.makedirs(zips_dir, exist_ok=True)

    print(f"\n{'='*62}")
    print(f"  GeoNames  →  Shapefile  |  Full Pipeline")
    print(f"  Base      : {downloads_folder}")
    print(f"  Zips      : {zips_dir}")
    print(f"  Output    : {geonames_dir}")
    print(f"{'='*62}\n")

    # ── 1. Discover country codes ─────────────────────────────────────
    if only:
        country_codes = [c.upper() for c in only]
        print(f"[INFO] Targeting {len(country_codes)} countries: {' '.join(country_codes)}\n")
    else:
        country_codes = scrape_country_codes()

    total = len(country_codes)

    # ── 2. Download phase ─────────────────────────────────────────────
    if not skip_download:
        print(f"\n── Downloading {total} zips (workers={workers}) ──────────────────\n")
        dl_ok = dl_cached = dl_err = 0

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(download_zip, cc, zips_dir, force_redownload): cc
                for cc in country_codes
            }
            done = 0
            for future in as_completed(futures):
                done += 1
                res = future.result()
                cc  = res["cc"]
                if res["status"] == "DOWNLOADED":
                    print(f"  [{done:>3}/{total}] ↓ {cc:<4}  {res['size']}")
                    dl_ok += 1
                elif res["status"] == "CACHED":
                    print(f"  [{done:>3}/{total}]   {cc:<4}  {res['size']}  (cached)")
                    dl_cached += 1
                else:
                    print(f"  [{done:>3}/{total}] ✗ {cc:<4}  ERROR: {res['error']}")
                    dl_err += 1

        print(f"\n  Downloaded: {dl_ok}  |  Cached: {dl_cached}  |  Errors: {dl_err}\n")
    else:
        print("[INFO] Skipping download phase (--skip-download)\n")

    # ── 3. Convert phase ──────────────────────────────────────────────
    print(f"── Converting {total} zips to shapefiles ────────────────────\n")
    cv_ok = cv_skip = cv_err = 0

    for i, cc in enumerate(country_codes, 1):
        print(f"  [{i:>3}/{total}] {cc:<4}", end=" ", flush=True)
        res = convert_zip(cc, zips_dir, geonames_dir)

        if res["status"] == "OK":
            print(f"✓  {res['features']:>8,} features")
            cv_ok += 1
        elif res["status"] == "SKIP":
            print(f"–  SKIPPED  ({res['error']})")
            cv_skip += 1
        else:
            print(f"✗  ERROR")
            print(f"           {res['error'].splitlines()[-1]}")
            cv_err += 1

    print(f"\n{'='*62}")
    print(f"  Converted : {cv_ok}  |  Skipped: {cv_skip}  |  Errors: {cv_err}")
    print(f"  Output    : {geonames_dir}")
    print(f"{'='*62}\n")

    # ── 4. Optional QGIS load ─────────────────────────────────────────
    try:
        from qgis.core import QgsVectorLayer, QgsProject
        answer = input("Load all layers into QGIS? [y/N]: ").strip().lower()
        if answer == "y":
            for cc in sorted(country_codes):
                shp = os.path.join(geonames_dir, cc, f"{cc}.shp")
                if os.path.isfile(shp):
                    layer = QgsVectorLayer(shp, cc, "ogr")
                    if layer.isValid():
                        QgsProject.instance().addMapLayer(layer)
                        print(f"  [QGIS] Added: {cc}")
    except ImportError:
        pass


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Download all GeoNames country zips and convert to shapefiles."
    )
    parser.add_argument(
        "--downloads", "-d", default=None,
        help="Path to your Downloads folder (auto-detected if not given)",
    )
    parser.add_argument(
        "--only", "-o", nargs="+", metavar="CC",
        help="Only process these country codes, e.g. --only KE UG TZ",
    )
    parser.add_argument(
        "--skip-download", action="store_true",
        help="Skip downloading; convert already-present zips only",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Re-download zips even if they already exist locally",
    )
    parser.add_argument(
        "--workers", "-w", type=int, default=4,
        help="Number of parallel download threads (default: 4)",
    )
    args = parser.parse_args()

    run(
        downloads_folder=args.downloads,
        only=args.only,
        skip_download=args.skip_download,
        workers=args.workers,
        force_redownload=args.force,
    )


if __name__ == "__main__":
    main()
