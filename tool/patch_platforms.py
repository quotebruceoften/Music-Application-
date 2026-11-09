"""Apply BeatMaker's settings to the platform folders that `flutter create` generates.

Run from the mobile/ folder after generating platforms. Safe to run more than once.
"""
import pathlib
import re

M = pathlib.Path(".")
NDK = "27.0.12077973"


def edit(path, fn):
    p = M / path
    if not p.exists():
        print("skip (missing):", path)
        return
    old = p.read_text()
    new = fn(old)
    if new != old:
        p.write_text(new)
        print("patched:", path)


# ---------------------------------------------------------------- Android
def manifest(s):
    perms = ["android.permission.INTERNET", "android.permission.RECORD_AUDIO"]
    for perm in perms:
        if perm not in s:
            s = s.replace("<application", f'<uses-permission android:name="{perm}"/>\n    <application', 1)
    # the engine runs at http://127.0.0.1 inside the app
    if "usesCleartextTraffic" not in s:
        s = s.replace("<application", '<application\n        android:usesCleartextTraffic="true"', 1)
    s = re.sub(r'android:label="[^"]*"', 'android:label="BeatMaker"', s, count=1)
    return s


def gradle(s):
    s = re.sub(r"minSdk\s*=\s*flutter\.minSdkVersion", "minSdk = 24", s)
    s = re.sub(r"minSdkVersion\s+flutter\.minSdkVersion", "minSdkVersion 24", s)
    s = re.sub(r"ndkVersion\s*=\s*flutter\.ndkVersion", f'ndkVersion = "{NDK}"', s)
    s = re.sub(r"ndkVersion\s+flutter\.ndkVersion", f'ndkVersion "{NDK}"', s)
    return s


edit("android/app/src/main/AndroidManifest.xml", manifest)
edit("android/app/build.gradle.kts", gradle)
edit("android/app/build.gradle", gradle)


# ---------------------------------------------------------------- iOS
def info_plist(s):
    add = ""
    if "NSMicrophoneUsageDescription" not in s:
        add += ("\t<key>NSMicrophoneUsageDescription</key>\n"
                "\t<string>BeatMaker records your voice to make your producer tag.</string>\n")
    if "NSAppTransportSecurity" not in s:
        add += ("\t<key>NSAppTransportSecurity</key>\n\t<dict>\n"
                "\t\t<key>NSAllowsLocalNetworking</key>\n\t\t<true/>\n\t</dict>\n")
    if add:
        i = s.rfind("</dict>")
        s = s[:i] + add + s[i:]
    s = re.sub(r"(<key>CFBundleDisplayName</key>\s*<string>)[^<]*(</string>)", r"\1BeatMaker\2", s)
    return s


def podfile(s):
    return re.sub(r"^#?\s*platform :ios, '[\d.]+'", "platform :ios, '13.0'", s, flags=re.M)


edit("ios/Runner/Info.plist", info_plist)
edit("ios/Podfile", podfile)


# ---------------------------------------------------------------- macOS
def entitlements(s):
    keys = ["com.apple.security.network.client", "com.apple.security.network.server",
            "com.apple.security.device.audio-input", "com.apple.security.files.user-selected.read-write"]
    add = "".join(f"\t<key>{k}</key>\n\t<true/>\n" for k in keys if k not in s)
    if add:
        i = s.rfind("</dict>")
        s = s[:i] + add + s[i:]
    return s


edit("macos/Runner/DebugProfile.entitlements", entitlements)
edit("macos/Runner/Release.entitlements", entitlements)


def mac_info(s):
    if "NSMicrophoneUsageDescription" in s:
        return s
    i = s.rfind("</dict>")
    return s[:i] + ("\t<key>NSMicrophoneUsageDescription</key>\n"
                    "\t<string>BeatMaker records your voice to make your producer tag.</string>\n") + s[i:]


edit("macos/Runner/Info.plist", mac_info)
print("done")
