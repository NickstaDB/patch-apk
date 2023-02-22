# :warning: Active fork for NickstaDB/patch-apk

As the original projects has been set to read-only, I've created an active fork which combines most interesting modifications. If you identify any issues, please open a ticket.

Original credit goes to @NickstaDB and significant modifications were made by myself and @jseigelis

# patch-apk - App Bundle/Split APK Aware Patcher for Objection #
An APK patcher, for use with [objection](https://github.com/sensepost/objection), that supports Android app bundles/split APKs. It automates the following:

1. Finding the full package name of an Android app.
2. Finding the APK path(s) and pulling them from the device.
3. Patching the APK(s) using `objection patchapk`.
	-  Combining split APKs into a single APK where necessary.
4. Enabling support for user-installed CA certificates (e.g. Burp Suite's CA Cert).
5. Uninstalling the original app from the device.
6. Installing the patched app to the device, ready for use with objection.

### Changelog ###

* **22nd February 2023:** Took over project and added various features:
  * Merged modifications from @jseigelis's fork
  * Removed support for outdated objection versions
  * Fixed bug for `--debug-output`
  * Added `--verbose` flag
  * Fixed bug with objection AndroidManifest extraction
  * Updated output format
  * Remove dependency on apksigner by using objection's signapk command

* **29th April 2021:** Implemented a fix for an issue with `apktool` where the handling of some resource XML elements changed and the `--use-aapt2` flag is required ([https://github.com/iBotPeaches/Apktool/issues/2462](https://github.com/iBotPeaches/Apktool/issues/2462)).
* **28th April 2021:** Fixed a bug with `objection` version detection when the `objection version` command output an update notice.
* **1st August 2020:** Updated for compatibility with `objection` version 1.9.3 and above and fixed a bug with line endings when retrieving package names from the Android device/emulator.
* **30th March 2020:** Fixed a bug where dummy resource IDs were assumed to all have true names. Added a hack to resolve an issue with duplicate entries in res/values/styles.xml after decompiling with apktool.
* **29th March 2020:** Added `--save-apk` parameter to save a copy of the unpatched single APK for use with other tools.
* **27th March 2020:** Initial release supporting split APKs and the `--no-enable-user-certs` flag.

## Usage ##
Install the target Android application on your device and connect it to your computer/VM so that `adb devices` can see it, then run:

```
python3 patch-apk.py {package-name}
```

The package-name parameter can be the fully-qualified package name of the Android app, such as `com.google.android.youtube`, or a partial package name, such as `tube`.

Along with injecting an instrumentation gadget, the script also automatically enables support for user-installed CA certificates by injecting a network security configuration file into the APK. To disable this functionality, pass the `--no-enable-user-certs` parameter on the command line.

### Examples ###
**Basic usage:** Simply install the target Android app on your device, make sure `adb devices` can see your device, then pass the package name to `patch-apk.py`.

```
$ python3 patch-apk.py com.whatsapp
Getting APK path(s) for package: com.whatsapp
[+] APK path: /data/app/com.whatsapp-NKLgchoExRFTDLkkbDqBGg==/base.apk

Pulling APK file(s) from device.
[+] Pulling: com.whatsapp-base.apk

Patching com.whatsapp-base.apk with objection.

Patching APK to enable support for user-installed CA certificates.

Uninstalling the original package from the device.

Installing the patched APK to the device.

Done, cleaning up temporary files.
```

When `patch-apk.py` is done, the installed app should be patched with objection and have support for user-installed CA certificates enabled. Launch the app on the device and run `objection explore` as you normally would to connect to the agent.

**Partial Package Name Matching:** Pass a partial package name to `patch-apk.py` and it'll automatically grab the correct package name or ask you to confirm from available options.

```
$ python3 patch-apk.py proxy

[!] Multiple matching packages installed, select the package to patch.

[1] org.proxydroid
[2] com.android.proxyhandler
Choice: 

```

**Patching Split APKs:** Split APKs are automatically detected and combined into a single APK before patching. Split APKs can be identified by multiple APK paths being returned by the `adb shell pm path` command as shown below.

```
$ adb shell pm path org.proxydroid
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/base.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.arm64_v8a.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.en.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.fr.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.nl.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.xxhdpi.apk
```

The following shows `patch-apk.py` detecting, rebuilding, and patching a split APK. Some output has been snipped for brevity. The `-v` flag has been set to show additional info.

```
$ python3 patch-apk.py org.proxydroid -v

[+] Retrieving APK path(s) for package: org.proxydroid
    [+] APK path: /data/app/~~FTVBmscrJiLerJdXIEa5tw==/org.proxydroid-KMq91nU1y9Qz8ZZAGM--RA==/base.apk
    [+] APK path: /data/app/~~FTVBmscrJiLerJdXIEa5tw==/org.proxydroid-KMq91nU1y9Qz8ZZAGM--RA==/split_config.arm64_v8a.apk
    [+] APK path: /data/app/~~FTVBmscrJiLerJdXIEa5tw==/org.proxydroid-KMq91nU1y9Qz8ZZAGM--RA==/split_config.en.apk
    [+] APK path: /data/app/~~FTVBmscrJiLerJdXIEa5tw==/org.proxydroid-KMq91nU1y9Qz8ZZAGM--RA==/split_config.fr.apk
    [+] APK path: /data/app/~~FTVBmscrJiLerJdXIEa5tw==/org.proxydroid-KMq91nU1y9Qz8ZZAGM--RA==/split_config.nl.apk
    [+] APK path: /data/app/~~FTVBmscrJiLerJdXIEa5tw==/org.proxydroid-KMq91nU1y9Qz8ZZAGM--RA==/split_config.xxhdpi.apk

[+] Pulling APK file(s) from device |################################| 6/6
    [+] Pulled: org.proxydroid-base.apk
    [+] Pulled: org.proxydroid-split_config.arm64_v8a.apk
    [+] Pulled: org.proxydroid-split_config.en.apk
    [+] Pulled: org.proxydroid-split_config.fr.apk
    [+] Pulled: org.proxydroid-split_config.nl.apk
    [+] Pulled: org.proxydroid-split_config.xxhdpi.apk

[!] App bundle/split APK detected, rebuilding as a single APK.

[+] Disassembling split APKs |################################| 6/6
    
    Extracted: /var/folders/t3/vz305z151ng8y2rwvpkx28xw0000gn/T/tmpyw7wl64i/org.proxydroid-base.apk
    Extracted: /var/folders/t3/vz305z151ng8y2rwvpkx28xw0000gn/T/tmpyw7wl64i/org.proxydroid-split_config.arm64_v8a.apk
    Extracted: /var/folders/t3/vz305z151ng8y2rwvpkx28xw0000gn/T/tmpyw7wl64i/org.proxydroid-split_config.en.apk
    Extracted: /var/folders/t3/vz305z151ng8y2rwvpkx28xw0000gn/T/tmpyw7wl64i/org.proxydroid-split_config.fr.apk
    Extracted: /var/folders/t3/vz305z151ng8y2rwvpkx28xw0000gn/T/tmpyw7wl64i/org.proxydroid-split_config.nl.apk
    Extracted: /var/folders/t3/vz305z151ng8y2rwvpkx28xw0000gn/T/tmpyw7wl64i/org.proxydroid-split_config.xxhdpi.apk

[+] Rebuilding as a single APK
    
    [+] Found public.xml in the base APK, fixing resource identifiers across split APKs.
    [+] Resolving 21 resource identifiers.
    [+] Located 21 true resource names.
    [+] Updated 21 dummy resource names with true names in the base APK.
    [+] Updated 47 references to dummy resource names in the base APK.
    [+] Disabling APK splitting in AndroidManifest.xml of base APK.
    [+] Fixing any improperly escaped ampersands.
    [+] Forcing all private resources to be public
    [+] Updated 350 private resources before building APK.
    [+] Rebuilding with 'apktool --use-aapt2'.

[+] Patching org.proxydroid-base.apk with objection.

[+] Patching APK to enable support for user-installed CA certificates.
    [+] Forcing all private resources to be public
    [+] Updated 351 private resources before building APK.
    [+] Rebuilding with 'apktool --use-aapt2'.
    [+] Zip aligning new APK.
    [+] Signing new APK.

[+] Uninstalling the original package from the device.

[+] Installing the patched APK to the device.

[+] Done
```

After `patch-apk.py` completes, we can run `adb shell pm path` again to verify that there is now a single patched APK installed on the device.

```
$ adb shell pm path org.proxydroid
package:/data/app/org.proxydroid-9NuZnT-lK3qM_IZQEHhTgA==/base.apk
```

By default, patch-apk will inject the frida gadget and modify the network security config. It is also possible to only perform an extraction by providing the `--extract-only` flag. Any split apks will still be merged and a local copy of the APK will be produced:

```
$ python3 patch-apk.py org.proxydroid --extract-only

[+] Retrieving APK path(s) for package: org.proxydroid

[+] Pulling APK file(s) from device |################################| 6/6

[!] App bundle/split APK detected, rebuilding as a single APK.

[+] Disassembling split APKs |################################| 6/6

[+] Rebuilding as a single APK

[+] Saving a copy of the APK to org.proxydroid.apk
```

## Combining Split APKs ##
Split APKs have been supported since Android 5/Lollipop (June 2014, API level 21). Essentially this allows an app to be split across multiple APK files, for example one might contain the main code and another might contain image resources for a given screen resolution. We can identify whether an app uses split APKs with the `adb shell pm path` command like so:

```
$ adb shell pm path org.proxydroid
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/base.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.arm64_v8a.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.en.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.fr.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.nl.apk
package:/data/app/~~TP7sglBuEoDc3yH0wpZdiA==/org.proxydroid-PCy1JxTMVJT3KmxVqaagGQ==/split_config.xxhdpi.apk
```

These can be combined into a single APK for use with other tools such as `objection patchapk`. This is done by `patch-apk.py` as follows:

**Step 1 - Extract APKs:** First, the individual APK files are pulled from the device and extracted using `apktool`.

**Step 2 - Combine Files:** Next, we walk the directory trees of all but `base.apk`, and move files and directories from the split APKs into the base APK.

**Step 3 - Fix Resource Identifiers:** Some resource names might only be defined in one of the split APKs, so we need to gather these up and update `base.apk` with the correct resource names.

**Step 4 - Disable Splitting:** The `AndroidManifest.xml` in `base.apk` is updated to disable support for splitting before rebuilding, signing, and zip aligning the APK.

More details can be found on [my blog](https://nickbloor.co.uk/2020/03/29/patching-android-split-apks/).
