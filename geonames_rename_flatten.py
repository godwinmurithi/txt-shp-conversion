"""
geonames_rename_flatten.py
==========================
Renames all country shapefiles from their ISO code to their full country name
and copies all files into a single flat folder ready for upload.

  Before:
    C:/Users/Admin/Documents/geonames/
      KE/  KE.shp, KE.dbf, KE.prj, KE.shx, KE.cpg
      UG/  UG.shp, UG.dbf ...
      TZ/  TZ.shp ...

  After:
    C:/Users/Admin/Documents/geonames/upload/
      Kenya_GeoNames_Places.shp
      Kenya_GeoNames_Places.dbf
      Kenya_GeoNames_Places.prj
      Kenya_GeoNames_Places.shx
      Kenya_GeoNames_Places.cpg
      Uganda_GeoNames_Places.shp
      Uganda_GeoNames_Places.dbf
      ...

Usage
-----
  python geonames_rename_flatten.py
  python geonames_rename_flatten.py --geonames-dir "C:/Users/Admin/Documents/geonames"
  python geonames_rename_flatten.py --suffix GeoNames_Features
"""

import os
import sys
import shutil
import argparse

# ── Full ISO 3166-1 alpha-2 → country name mapping ───────────────────────────
COUNTRY_NAMES = {
    "AD": "Andorra", "AE": "United_Arab_Emirates", "AF": "Afghanistan",
    "AG": "Antigua_and_Barbuda", "AI": "Anguilla", "AL": "Albania",
    "AM": "Armenia", "AO": "Angola", "AQ": "Antarctica",
    "AR": "Argentina", "AS": "American_Samoa", "AT": "Austria",
    "AU": "Australia", "AW": "Aruba", "AX": "Aland_Islands",
    "AZ": "Azerbaijan", "BA": "Bosnia_and_Herzegovina", "BB": "Barbados",
    "BD": "Bangladesh", "BE": "Belgium", "BF": "Burkina_Faso",
    "BG": "Bulgaria", "BH": "Bahrain", "BI": "Burundi",
    "BJ": "Benin", "BL": "Saint_Barthelemy", "BM": "Bermuda",
    "BN": "Brunei", "BO": "Bolivia", "BQ": "Caribbean_Netherlands",
    "BR": "Brazil", "BS": "Bahamas", "BT": "Bhutan",
    "BV": "Bouvet_Island", "BW": "Botswana", "BY": "Belarus",
    "BZ": "Belize", "CA": "Canada", "CC": "Cocos_Islands",
    "CD": "DR_Congo", "CF": "Central_African_Republic", "CG": "Republic_of_Congo",
    "CH": "Switzerland", "CI": "Ivory_Coast", "CK": "Cook_Islands",
    "CL": "Chile", "CM": "Cameroon", "CN": "China",
    "CO": "Colombia", "CR": "Costa_Rica", "CU": "Cuba",
    "CV": "Cape_Verde", "CW": "Curacao", "CX": "Christmas_Island",
    "CY": "Cyprus", "CZ": "Czech_Republic", "DE": "Germany",
    "DJ": "Djibouti", "DK": "Denmark", "DM": "Dominica",
    "DO": "Dominican_Republic", "DZ": "Algeria", "EC": "Ecuador",
    "EE": "Estonia", "EG": "Egypt", "EH": "Western_Sahara",
    "ER": "Eritrea", "ES": "Spain", "ET": "Ethiopia",
    "FI": "Finland", "FJ": "Fiji", "FK": "Falkland_Islands",
    "FM": "Micronesia", "FO": "Faroe_Islands", "FR": "France",
    "GA": "Gabon", "GB": "United_Kingdom", "GD": "Grenada",
    "GE": "Georgia", "GF": "French_Guiana", "GG": "Guernsey",
    "GH": "Ghana", "GI": "Gibraltar", "GL": "Greenland",
    "GM": "Gambia", "GN": "Guinea", "GP": "Guadeloupe",
    "GQ": "Equatorial_Guinea", "GR": "Greece", "GS": "South_Georgia",
    "GT": "Guatemala", "GU": "Guam", "GW": "Guinea_Bissau",
    "GY": "Guyana", "HK": "Hong_Kong", "HM": "Heard_Island",
    "HN": "Honduras", "HR": "Croatia", "HT": "Haiti",
    "HU": "Hungary", "ID": "Indonesia", "IE": "Ireland",
    "IL": "Israel", "IM": "Isle_of_Man", "IN": "India",
    "IO": "British_Indian_Ocean_Territory", "IQ": "Iraq", "IR": "Iran",
    "IS": "Iceland", "IT": "Italy", "JE": "Jersey",
    "JM": "Jamaica", "JO": "Jordan", "JP": "Japan",
    "KE": "Kenya", "KG": "Kyrgyzstan", "KH": "Cambodia",
    "KI": "Kiribati", "KM": "Comoros", "KN": "Saint_Kitts_and_Nevis",
    "KP": "North_Korea", "KR": "South_Korea", "KW": "Kuwait",
    "KY": "Cayman_Islands", "KZ": "Kazakhstan", "LA": "Laos",
    "LB": "Lebanon", "LC": "Saint_Lucia", "LI": "Liechtenstein",
    "LK": "Sri_Lanka", "LR": "Liberia", "LS": "Lesotho",
    "LT": "Lithuania", "LU": "Luxembourg", "LV": "Latvia",
    "LY": "Libya", "MA": "Morocco", "MC": "Monaco",
    "MD": "Moldova", "ME": "Montenegro", "MF": "Saint_Martin",
    "MG": "Madagascar", "MH": "Marshall_Islands", "MK": "North_Macedonia",
    "ML": "Mali", "MM": "Myanmar", "MN": "Mongolia",
    "MO": "Macao", "MP": "Northern_Mariana_Islands", "MQ": "Martinique",
    "MR": "Mauritania", "MS": "Montserrat", "MT": "Malta",
    "MU": "Mauritius", "MV": "Maldives", "MW": "Malawi",
    "MX": "Mexico", "MY": "Malaysia", "MZ": "Mozambique",
    "NA": "Namibia", "NC": "New_Caledonia", "NE": "Niger",
    "NF": "Norfolk_Island", "NG": "Nigeria", "NI": "Nicaragua",
    "NL": "Netherlands", "NO": "Norway", "NP": "Nepal",
    "NR": "Nauru", "NU": "Niue", "NZ": "New_Zealand",
    "OM": "Oman", "PA": "Panama", "PE": "Peru",
    "PF": "French_Polynesia", "PG": "Papua_New_Guinea", "PH": "Philippines",
    "PK": "Pakistan", "PL": "Poland", "PM": "Saint_Pierre_and_Miquelon",
    "PN": "Pitcairn", "PR": "Puerto_Rico", "PS": "Palestine",
    "PT": "Portugal", "PW": "Palau", "PY": "Paraguay",
    "QA": "Qatar", "RE": "Reunion", "RO": "Romania",
    "RS": "Serbia", "RU": "Russia", "RW": "Rwanda",
    "SA": "Saudi_Arabia", "SB": "Solomon_Islands", "SC": "Seychelles",
    "SD": "Sudan", "SE": "Sweden", "SG": "Singapore",
    "SH": "Saint_Helena", "SI": "Slovenia", "SJ": "Svalbard_and_Jan_Mayen",
    "SK": "Slovakia", "SL": "Sierra_Leone", "SM": "San_Marino",
    "SN": "Senegal", "SO": "Somalia", "SR": "Suriname",
    "SS": "South_Sudan", "ST": "Sao_Tome_and_Principe", "SV": "El_Salvador",
    "SX": "Sint_Maarten", "SY": "Syria", "SZ": "Eswatini",
    "TC": "Turks_and_Caicos_Islands", "TD": "Chad", "TF": "French_Southern_Territories",
    "TG": "Togo", "TH": "Thailand", "TJ": "Tajikistan",
    "TK": "Tokelau", "TL": "Timor_Leste", "TM": "Turkmenistan",
    "TN": "Tunisia", "TO": "Tonga", "TR": "Turkey",
    "TT": "Trinidad_and_Tobago", "TV": "Tuvalu", "TW": "Taiwan",
    "TZ": "Tanzania", "UA": "Ukraine", "UG": "Uganda",
    "UM": "US_Minor_Outlying_Islands", "US": "United_States", "UY": "Uruguay",
    "UZ": "Uzbekistan", "VA": "Vatican_City", "VC": "Saint_Vincent_and_the_Grenadines",
    "VE": "Venezuela", "VG": "British_Virgin_Islands", "VI": "US_Virgin_Islands",
    "VN": "Vietnam", "VU": "Vanuatu", "WF": "Wallis_and_Futuna",
    "WS": "Samoa", "YE": "Yemen", "YT": "Mayotte",
    "ZA": "South_Africa", "ZM": "Zambia", "ZW": "Zimbabwe",
}

SHAPEFILE_EXTENSIONS = [".shp", ".dbf", ".prj", ".shx", ".cpg", ".qpj", ".sbn", ".sbx"]


# ── Core rename + flatten ─────────────────────────────────────────────────────

def rename_and_flatten(geonames_dir: str, suffix: str = "GeoNames_Places") -> str:
    """
    Rename all <CC>/<CC>.shp files to <CountryName>_<suffix>.shp
    and copy all shapefile components into a single upload/ folder.

    Returns the path to the upload folder.
    """
    geonames_dir = os.path.abspath(geonames_dir)
    upload_dir   = os.path.join(geonames_dir, "upload")
    os.makedirs(upload_dir, exist_ok=True)

    # Find all country subfolders (2-letter names)
    subfolders = sorted([
        f for f in os.listdir(geonames_dir)
        if os.path.isdir(os.path.join(geonames_dir, f))
        and len(f) == 2
        and f.upper() != "upload".upper()
    ])

    if not subfolders:
        print(f"[WARN] No country folders found in: {geonames_dir}")
        return upload_dir

    total = len(subfolders)
    ok = skipped = errors = 0

    print(f"\n{'='*62}")
    print(f"  GeoNames  →  Rename & Flatten for Upload")
    print(f"  Source : {geonames_dir}")
    print(f"  Output : {upload_dir}")
    print(f"  Suffix : {suffix}")
    print(f"  Found  : {total} country folders")
    print(f"{'='*62}\n")

    for i, cc in enumerate(subfolders, 1):
        cc_upper     = cc.upper()
        country_name = COUNTRY_NAMES.get(cc_upper)

        if not country_name:
            print(f"  [{i:>3}/{total}] {cc:<4}  – SKIPPED (unknown country code)")
            skipped += 1
            continue

        new_base    = f"{country_name}_{suffix}"
        source_base = os.path.join(geonames_dir, cc, cc_upper)

        # Check the .shp exists
        if not os.path.isfile(source_base + ".shp"):
            print(f"  [{i:>3}/{total}] {cc:<4}  – SKIPPED (no .shp found in folder)")
            skipped += 1
            continue

        # Copy and rename each shapefile component
        copied = []
        try:
            for ext in SHAPEFILE_EXTENSIONS:
                src = source_base + ext
                if os.path.isfile(src):
                    dst = os.path.join(upload_dir, new_base + ext)
                    shutil.copy2(src, dst)
                    copied.append(ext)

            print(f"  [{i:>3}/{total}] {cc:<4}  ✓  {new_base}  ({', '.join(copied)})")
            ok += 1

        except Exception as e:
            print(f"  [{i:>3}/{total}] {cc:<4}  ✗  ERROR: {e}")
            errors += 1

    print(f"\n{'='*62}")
    print(f"  Done    : {ok} renamed  |  {skipped} skipped  |  {errors} errors")
    print(f"  Upload  : {upload_dir}")
    print(f"{'='*62}\n")

    return upload_dir


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Rename GeoNames shapefiles to full country names and flatten into upload/ folder."
    )
    parser.add_argument(
        "--geonames-dir", "-d",
        default=r"C:\Users\Admin\Documents\geonames",
        help="Path to your geonames folder (default: C:\\Users\\Admin\\Documents\\geonames)",
    )
    parser.add_argument(
        "--suffix", "-s",
        default="GeoNames_Places",
        help="Suffix appended after country name (default: GeoNames_Places)",
    )
    args = parser.parse_args()

    rename_and_flatten(
        geonames_dir=args.geonames_dir,
        suffix=args.suffix,
    )


if __name__ == "__main__":
    main()
