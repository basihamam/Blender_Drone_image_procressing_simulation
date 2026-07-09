"""
BAGIMLILIK KONTROLU VE OTOMATIK KURULUM
=========================================
deneme_02_7.py / pybullet_backend.py calismadan once bunu calistir:

    python check_requirements.py

Eksik paketleri otomatik `pip install` ile kurar. Kurulum sonrasi ayni
process icinde import'u tekrar dener (yeni terminal acmana gerek kalmaz).
"""

import sys
import subprocess
import importlib

# (pip_adi, import_adi) — bazilarinda ikisi farkli (ör. PIL -> Pillow)
REQUIRED_PACKAGES = [
    ("numpy",      "numpy"),
    ("opencv-python", "cv2"),
    ("Pillow",     "PIL"),
    ("pygame",     "pygame"),
    ("pybullet",   "pybullet"),
]


def check_and_install():
    missing = []

    print("Paketler kontrol ediliyor...\n")
    for pip_name, import_name in REQUIRED_PACKAGES:
        try:
            importlib.import_module(import_name)
            print(f"  [OK]     {pip_name}")
        except ImportError:
            print(f"  [EKSIK]  {pip_name}")
            missing.append(pip_name)

    if not missing:
        print("\nTum bagimliliklar zaten kurulu.")
        return True

    print(f"\n{len(missing)} paket eksik, kuruluyor: {', '.join(missing)}\n")

    for pip_name in missing:
        print(f"--- kuruluyor: {pip_name} ---")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", pip_name],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"[HATA] {pip_name} kurulamadi:\n{result.stderr}")
            return False
        print(f"[TAMAM] {pip_name} kuruldu.\n")

    print("Kurulum tamamlandi, import'lar tekrar deneniyor...\n")
    still_missing = []
    for pip_name, import_name in missing_import_pairs(missing):
        try:
            importlib.invalidate_caches()
            importlib.import_module(import_name)
            print(f"  [OK]  {pip_name} (kurulum sonrasi dogrulandi)")
        except ImportError as e:
            print(f"  [HALA EKSIK]  {pip_name}: {e}")
            still_missing.append(pip_name)

    if still_missing:
        print(f"\nBazi paketler hala import edilemiyor: {still_missing}")
        print("Elle deneyin: pip install " + " ".join(still_missing))
        return False

    print("\nTum bagimliliklar hazir. Programi calistirabilirsin.")
    return True


def missing_import_pairs(missing_pip_names):
    lookup = {pip: imp for pip, imp in REQUIRED_PACKAGES}
    return [(name, lookup[name]) for name in missing_pip_names]


if __name__ == "__main__":
    ok = check_and_install()
    sys.exit(0 if ok else 1)
