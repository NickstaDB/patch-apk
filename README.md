# patch-apk - App Bundle/Split APK Aware Patcher for Objection #
An APK patcher, for use with [objection](https://github.com/sensepost/objection), that supports Android app bundles/split APKs. It automates the following:

1. Finding the full package name of an Android app.
2. Finding the APK path(s) and pulling them from the device.
3. Patching the APK(s) using `objection patchapk`.
	-  Combining split APKs into a single APK where necessary.
4. Enabling support for user-installed CA certificates (e.g. Burp Suite's CA Cert).
5. Uninstalling the original app from the device.
6. Installing the patched app to the device, ready for use with objection.

## Usage ##
Install the target Android application on your device and connect it to your computer/VM so that `adb devices` can see it, then run:

`python3 patch-apk.py {package-name}`

The package-name parameter can be the fully-qualified package name of the Android app, such as `com.google.android.youtube`, or a partial package name, such as `tube`.

Along with injecting an instrumentation gadget, the script also automatically enables support for user-installed CA certificates by injecting a network security configuration file into the APK. To disable this functionality, pass the `--no-enable-user-certs` parameter on the command line.
