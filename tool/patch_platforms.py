"""Apply BeatMaker's settings to the platform folders that `flutter create` generates.

Run from the mobile/ folder after generating platforms. Safe to run more than once.
"""
import pathlib
import re
import shutil

M = pathlib.Path(".")
# Plugins (serious_python, audioplayers, record...) need at least this NDK; newer is fine.
NDK = "28.2.13676358"
MIN_COMPILE_SDK = 36


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


# Some plugins (serious_python_android 0.9.x) compile against an old SDK, which fails
# AGP's AAR metadata check. Raise any plugin's compileSdk to at least MIN_COMPILE_SDK.
# Registered before `evaluationDependsOn(":app")` so it runs before AGP finalizes.
RAISE_SDK = f"""// BeatMaker: raise old plugin compileSdk (added by tool/patch_platforms.py)
subprojects {{
    afterEvaluate {{
        if (name == "app") return@afterEvaluate
        val ext = extensions.findByName("android") ?: return@afterEvaluate
        try {{
            val cur = ext.javaClass.getMethod("getCompileSdkVersion").invoke(ext) as String?
            val level = cur?.substringAfter("android-")?.toIntOrNull() ?: 0
            if (level < {MIN_COMPILE_SDK}) {{
                ext.javaClass.getMethod("compileSdkVersion", Int::class.javaPrimitiveType).invoke(ext, {MIN_COMPILE_SDK})
            }}
        }} catch (e: Exception) {{
            logger.warn("Could not raise compileSdk for $name: $e")
        }}
    }}
}}
"""


def root_gradle(s):
    if "BeatMaker: raise old plugin compileSdk" in s:
        return s
    anchor = "subprojects {\n    project.evaluationDependsOn"
    if anchor in s:
        return s.replace(anchor, RAISE_SDK + anchor, 1)
    return RAISE_SDK + "\n" + s



edit("android/build.gradle.kts", root_gradle)
edit("android/app/src/main/AndroidManifest.xml", manifest)
def legacy_packaging(kts):
    # serious_python ships Python's stdlib and site-packages as zip files named lib*.so and
    # reads them from nativeLibraryDir. Android only puts them there when native libs are
    # extracted at install (extractNativeLibs="true"); without it Python can't start.
    block = ("\n    packaging {\n        jniLibs {\n            useLegacyPackaging = true\n        }\n    }\n" if kts else
             "\n    packagingOptions {\n        jniLibs {\n            useLegacyPackaging true\n        }\n    }\n")

    def fn(s):
        if "useLegacyPackaging" in s:
            return s
        return s.replace("android {\n", "android {" + block, 1)
    return fn


edit("android/app/build.gradle.kts", gradle)
edit("android/app/build.gradle", gradle)
# serious_python 6 loads Python's native modules straight from the APK, so native libs no
# longer need extracting at install (legacy_packaging is kept for older serious_python).


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


IOS_MIN, MACOS_MIN = "15.0", "12.0"  # serious_python 6 needs iOS 15 / macOS 12


def podfile(s):
    return re.sub(r"^#?\s*platform :ios, '[\d.]+'", f"platform :ios, '{IOS_MIN}'", s, flags=re.M)


def mac_podfile(s):
    return re.sub(r"^#?\s*platform :osx, '[\d.]+'", f"platform :osx, '{MACOS_MIN}'", s, flags=re.M)


def ensure_podfile(rel, template_name):
    """flutter create doesn't always write a Podfile; start from Flutter's own template."""
    if (M / rel).exists() or not (M / rel).parent.exists():
        return
    flutter = shutil.which("flutter")
    if not flutter:
        return
    tpl = pathlib.Path(flutter).resolve().parent.parent / "packages/flutter_tools/templates/cocoapods" / template_name
    if tpl.exists():
        (M / rel).write_text(tpl.read_text())
        print("created:", rel)


def deployment_target(key, version):
    return lambda s: re.sub(key + r" = [\d.]+;", f"{key} = {version};", s)


edit("ios/Runner/Info.plist", info_plist)
ensure_podfile("ios/Podfile", "Podfile-ios")
edit("ios/Podfile", podfile)
edit("ios/Runner.xcodeproj/project.pbxproj", deployment_target("IPHONEOS_DEPLOYMENT_TARGET", IOS_MIN))


# ---------------------------------------------------------------- macOS
def entitlements(s):
    keys = ["com.apple.security.network.client", "com.apple.security.network.server",
            "com.apple.security.device.audio-input", "com.apple.security.files.user-selected.read-write"]
    add = "".join(f"\t<key>{k}</key>\n\t<true/>\n" for k in keys if k not in s)
    if add:
        i = s.rfind("</dict>")
        s = s[:i] + add + s[i:]
    return s


ensure_podfile("macos/Podfile", "Podfile-macos")
edit("macos/Podfile", mac_podfile)
edit("macos/Runner.xcodeproj/project.pbxproj", deployment_target("MACOSX_DEPLOYMENT_TARGET", MACOS_MIN))
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
