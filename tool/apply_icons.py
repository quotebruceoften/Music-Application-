"""Resize mobile/assets/icon.png into every app-icon file that `flutter create` generated."""
import glob
import pathlib

from PIL import Image

M = pathlib.Path(__file__).resolve().parent.parent / "mobile"
master = Image.open(M / "assets" / "icon.png").convert("RGB")
patterns = [
    "android/app/src/main/res/mipmap-*/ic_launcher.png",
    "ios/Runner/Assets.xcassets/AppIcon.appiconset/*.png",
    "macos/Runner/Assets.xcassets/AppIcon.appiconset/*.png",
    "web/icons/*.png",
]
n = 0
for pat in patterns:
    for f in glob.glob(str(M / pat)):
        with Image.open(f) as old:
            size = old.size
        master.resize(size, Image.LANCZOS).save(f)
        n += 1
print(f"icons updated: {n}")
