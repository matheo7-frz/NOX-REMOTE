"""Vérifie que les DLL Qt WebEngine trouvent toutes leurs fonctions dans les autres DLL Qt.
Code de sortie 0 = compatible, 1 = incompatible (évite le plantage « point d'entrée introuvable »)."""
import pathlib
import sys

import pefile

bindir = pathlib.Path(sys.argv[1])
exports_cache = {}


def exports(dll):
    if dll not in exports_cache:
        path = bindir / dll
        if not path.exists():
            exports_cache[dll] = None
        else:
            pe = pefile.PE(str(path), fast_load=True)
            pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_EXPORT"]])
            names = set()
            if hasattr(pe, "DIRECTORY_ENTRY_EXPORT"):
                for e in pe.DIRECTORY_ENTRY_EXPORT.symbols:
                    if e.name:
                        names.add(e.name.decode())
            exports_cache[dll] = names
    return exports_cache[dll]


targets = sorted(bindir.glob("Qt6WebEngine*.dll")) + sorted(bindir.glob("Qt6Pdf*.dll"))
if not targets:
    print("Aucune DLL WebEngine")
    sys.exit(1)

missing = 0
for dll in targets:
    pe = pefile.PE(str(dll), fast_load=True)
    pe.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY["IMAGE_DIRECTORY_ENTRY_IMPORT"]])
    for entry in getattr(pe, "DIRECTORY_ENTRY_IMPORT", []):
        lib = entry.dll.decode()
        if not lib.lower().startswith("qt6"):
            continue
        have = exports(lib)
        if have is None:
            print(f"{dll.name}: {lib} absente")
            missing += 1
            continue
        for imp in entry.imports:
            if imp.name and imp.name.decode() not in have:
                print(f"{dll.name}: {lib} -> {imp.name.decode()} MANQUANT")
                missing += 1

print(f"{len(targets)} DLL vérifiées, {missing} problème(s)")
sys.exit(1 if missing else 0)
