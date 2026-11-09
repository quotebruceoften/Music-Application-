"""Copy files from a fresh `flutter create` template into mobile/ without overwriting ours."""
import os
import shutil
import sys

src, dst = sys.argv[1], sys.argv[2]
SKIP_TOP = {"lib", "test", "pubspec.yaml", "README.md", ".dart_tool", "build"}
added = 0
for root, dirs, files in os.walk(src):
    rel = os.path.relpath(root, src)
    top = rel.split(os.sep)[0]
    if top in SKIP_TOP:
        dirs[:] = []
        continue
    if rel == ".":
        files = [f for f in files if f not in SKIP_TOP]
    for f in files:
        target = os.path.join(dst, rel, f)
        if not os.path.exists(target):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(os.path.join(root, f), target)
            added += 1
print(f"template files added: {added}")
