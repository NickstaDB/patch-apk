#!/usr/bin/python3
import argparse
import os
import pkg_resources
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree
import re
from progress.bar import Bar
from termcolor import colored

SUPPORTED_VERSION = "2.6.1"
NULL_DECODED_DRAWABLE_COLOR = "#000000ff"

####################
# Main()
####################
def main():
    # Grab argz
    args = getArgs()

    # Warn for unexpected version
    apktoolVersion = getApktoolVersion()
    if apktoolVersion != pkg_resources.parse_version(SUPPORTED_VERSION):
        warningPrint("WARNING: currently installed apktool version " + str(apktoolVersion) + " is not the same as what this version of this script is developed for (" + SUPPORTED_VERSION + "), you may suffer from build failures, bugs, and obsolete patches")

    # Check that dependencies are available
    checkDependencies(args.extract_only)
    
    # Verify the package name and ensure it's installed (also supports partial package names)
    pkgname = verifyPackageName(args.pkgname)
    
    # Get the APK path(s) from the device
    apkpaths = getAPKPathsForPackage(pkgname)
    
    # Create a temp directory to work from
    with tempfile.TemporaryDirectory() as tmppath:
        # Get the APK to patch. Combine app bundles/split APKs into a single APK.
        apkfile = getTargetAPK(pkgname, apkpaths, tmppath, args.disable_styles_hack, args.extract_only)
        
        # Save the APK if requested
        if args.save_apk is not None or args.extract_only:
            targetName = args.save_apk if args.save_apk is not None else pkgname + ".apk"
            print("\n[+] Saving a copy of the APK to " + targetName)
            shutil.copy(apkfile, targetName)

            if args.extract_only:
                os.remove(apkfile)
                return
        
        # Patch the target APK with objection
        print("\n[+] Patching " + apkfile.split(os.sep)[-1] + " with objection.")
        if subprocess.run(["objection", "patchapk", "--skip-resources", "--ignore-nativelibs", "-s", apkfile], stdout=getStdout(), stderr=getStdout()).returncode != 0:
            print("\n[+] Objection patching failed, trying alternative approach")
            warningPrint("[!] If you get an error, the application might not have a launchable activity")
            
            # Try without --skip-resources, since objection potentially wasn't able to identify the starting activity
            # There could have been another reason for the failure, but it's a sensible fallback
            assertSubprocessSuccessfulRun(["objection", "patchapk", "--ignore-nativelibs", "-s", apkfile])
    
        os.remove(apkfile)
        shutil.move(apkfile[:-4] + ".objection.apk", apkfile)
        
        # Enable support for user-installed CA certs (e.g. Burp Suite CA installed on device by user)
        if not args.no_enable_user_certs:
            enableUserCerts(apkfile)
        
        # Uninstall the original package from the device
        print("\n[+] Uninstalling the original package from the device.")
        assertSubprocessSuccessfulRun(["adb", "uninstall", pkgname])
        
        # Install the patched APK
        print("\n[+] Installing the patched APK to the device.")
        assertSubprocessSuccessfulRun(["adb", "install", apkfile])
        
        # Done
        print("\n[+] Done")

def assertSubprocessSuccessfulRun(args):
    if subprocess.run(args, stdout=getStdout(), stderr=getStdout()).returncode != 0:
        abort(f"Error: Failed to run {' '.join(args)}.\nRun with --debug-output for more information.")
        
####################
# Check that required dependencies are present:
# -> Tools used
# -> Android device connected
# -> Keystore
####################
def checkDependencies(extract_only):
    deps = ["adb", "apktool", "aapt"]

    if not extract_only:
        deps += ["objection", "zipalign", "apksigner"]

    missing = []
    for dep in deps:
        if shutil.which(dep) is None:
            missing.append(dep)
    if len(missing) > 0:
        abort("Error, missing dependencies, ensure the following commands are available on the PATH: " + (", ".join(missing)))
    
    # Verify that an Android device is connected
    proc = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE)
    if proc.returncode != 0:
        abort("Error: Failed to run 'adb devices'.")
    deviceOut = proc.stdout.decode("utf-8")
    if len(deviceOut.strip().split(os.linesep)) == 1:
        abort("Error, no Android device connected (\"adb devices\"), connect a device first.")
    
    # Check that the included keystore exists
    if not os.path.exists(os.path.realpath(os.path.join(os.path.realpath(__file__), "..", "data", "patch-apk.keystore"))):
        abort("Error, the keystore was not found at " + os.path.realpath(os.path.join(os.path.realpath(__file__), "..", "data", "patch-apk.keystore")) + ", please clone the repository or get the keystore file and place it at this location.")

####################
# Grab command line parameters
####################
def getArgs():
    # Only parse args once
    if not hasattr(getArgs, "parsed_args"):
        # Parse the command line
        parser = argparse.ArgumentParser(
            description="patch-apk - Pull and patch Android apps for use with objection/frida. Supports split APKs."
        )
        parser.add_argument("--no-enable-user-certs", help="Prevent patch-apk from enabling user-installed certificate support via network security config in the patched APK.", action="store_true")
        parser.add_argument("--save-apk", help="Save a copy of the APK (or single APK) prior to patching for use with other tools. APK will be saved under the given name.")
        parser.add_argument("--extract-only", help="Disable including objection and pushing modified APK to device.", action="store_true")
        parser.add_argument("--disable-styles-hack", help="Disable the styles hack that removes duplicate entries from res/values/styles.xml.", action="store_true")
        parser.add_argument("--debug-output", help="Enable debug output.", action="store_true")
        parser.add_argument("-v", "--verbose", help="Enable verbose output.", action="store_true")
        parser.add_argument("pkgname", help="The name, or partial name, of the package to patch (e.g. com.foo.bar).")
        
        # Store the parsed args
        getArgs.parsed_args = parser.parse_args()
    
    # Return the parsed command line args
    return getArgs.parsed_args

####################
# Debug print
####################
def dbgPrint(msg):
    if getArgs().debug_output:
        print(msg)

####################
# Warning print
####################
def warningPrint(msg):
    print(colored(msg, "yellow"))


####################
# Abort will print given error message and exit the app
####################
def abort(msg):
    print(colored(msg, "red"))
    sys.exit(1)

####################
# Get the stdout target for subprocess calls. Set to DEVNULL unless debug output is enabled.
####################
def getStdout():
    if getArgs().debug_output:
        return None
    else:
        return subprocess.DEVNULL

####################
# Get apktool version
####################
def getApktoolVersion():
    proc = subprocess.run(["apktool", "-version"], stdout=subprocess.PIPE)
    return pkg_resources.parse_version(proc.stdout.decode("utf-8").strip().split("-")[0].strip())

####################
# Wrapper to run apktool platform-independently, complete with a dirty hack to fix apktool's dirty hack.
####################
def runApkTool(params):
    if os.name == "nt":
        args = ["apktool.bat"]
        args.extend(params)
        
        # apktool.bat has a dirty hack that execute "pause", so we need a dirty hack to kill the pause command...
        proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=getStdout())
        proc.communicate(b"\r\n")
        return proc
    else:
        args = ["apktool"]
        args.extend(params)
        return subprocess.run(args, stdout=getStdout())

####################
# Fix private resources preventing builds (apktool wontfix: https://github.com/iBotPeaches/Apktool/issues/2761)
####################
def fixPrivateResources(baseapkdir):
    verbosePrint("[+] Forcing all private resources to be public")
    updated = 0
    for (root, dirs, files) in os.walk(os.path.join(baseapkdir, "res")):
        for f in files:
            if f.lower().endswith(".xml"):
                rawREReplace(os.path.join(root, f), '@android', '@*android')
                updated += 1
    if updated > 0:
        verbosePrint("[+] Updated " + str(updated) + " private resources before building APK.")

####################
# Build the APK
####################
def build(baseapkdir):
    # Fix private resources preventing builds (apktool wontfix: https://github.com/iBotPeaches/Apktool/issues/2761)
    fixPrivateResources(baseapkdir)

    if os.path.exists(os.path.join(baseapkdir, "res", "navigation")) or getApktoolVersion() > pkg_resources.parse_version("2.4.2"):
        verbosePrint("[+] Rebuilding with 'apktool --use-aapt2'.")
        ret = runApkTool(["--use-aapt2", "b", baseapkdir])
        if ret.returncode != 0:
            abort("Error: Failed to run 'apktool b " + baseapkdir + "'.\nRun with --debug-output for more information.")
    else:
        verbosePrint("[+] Rebuilding APK with apktool.")
        ret = runApkTool(["b", baseapkdir])
        if ret.returncode != 0:
            abort("Error: Failed to run 'apktool b " + baseapkdir + "'.\nRun with --debug-output for more information.")

####################
# Sign the APK with apksigner and zip align
# Fixes https://github.com/NickstaDB/patch-apk/issues/31 by no longer using jarsigner (V1 APK signatures)
####################
def signAndZipAlign(baseapkdir, baseapkfilename):
    # Zip align the new APK
    verbosePrint("[+] Zip aligning new APK.")
    assertSubprocessSuccessfulRun(["zipalign", "-f", "4", os.path.join(baseapkdir, "dist", baseapkfilename),
        os.path.join(baseapkdir, "dist", baseapkfilename[:-4] + "-aligned.apk")])
    shutil.move(os.path.join(baseapkdir, "dist", baseapkfilename[:-4] + "-aligned.apk"), os.path.join(baseapkdir, "dist", baseapkfilename))

    # Sign the new APK
    verbosePrint("[+] Signing new APK.")
    apkpath = os.path.join(baseapkdir, "dist", baseapkfilename)
    assertSubprocessSuccessfulRun(["objection", "signapk", apkpath])

####################
# Verify the package name - checks whether the target package is installed
# on the device or if an exact match is not found presents the options to
# the user for selection.
####################
def verifyPackageName(pkgname):
    # Get a list of installed packages matching the given name
    packages = []
    proc = subprocess.run(["adb", "shell", "pm", "list", "packages"], stdout=subprocess.PIPE)
    if proc.returncode != 0:
        abort("Error: Failed to run 'adb shell pm list packages'.")
    out = proc.stdout.decode("utf-8")
    for line in out.split(os.linesep):
        if line.startswith("package:"):
            line = line[8:].strip()
            if pkgname.lower() in line.lower():
                packages.append(line)
    
    # Bail out if no matching packages were found
    if len(packages) == 0:
        abort("Error, no packages found on the device matching the search term '" + pkgname + "'.\nRun 'adb shell pm list packages' to verify installed package names.")
    
    # Return the target package name, offering a choice to the user if necessary
    if len(packages) == 1:
        return packages[0]
    else:
        warningPrint("\n[!] Multiple matching packages installed, select the package to patch.\n")
        choice = -1
        while choice == -1:
            for i in range(len(packages)):
                print("[" + str(i + 1) + "] " + packages[i])
            choice = input("Choice: ")
            if not choice.isnumeric() or int(choice) < 1 or int(choice) > len(packages):
                print("Invalid choice.\n")
                choice = -1
        return packages[int(choice) - 1]

####################
# Get the APK path(s) on the device for the given package name.
####################
def getAPKPathsForPackage(pkgname):
    print("\n[+] Retrieving APK path(s) for package: " + pkgname)
    paths = []
    proc = subprocess.run(["adb", "shell", "pm", "path", pkgname], stdout=subprocess.PIPE)
    if proc.returncode != 0:
        abort("Error: Failed to run 'adb shell pm path " + pkgname + "'.")
    out = proc.stdout.decode("utf-8")

    for line in out.split(os.linesep):
        if line.startswith("package:"):
            line = line[8:].strip()
            verbosePrint("[+] APK path: " + line)
            paths.append(line)

    return paths

####################
# Pull the APK file(s) for the package and return the local file path to work with.
# If the package is an app bundle/split APK, combine the APKs into a single APK.
####################
def getTargetAPK(pkgname, apkpaths, tmppath, disableStylesHack, extract_only):
    # Pull the APKs from the device
    print("")
    bar = Bar('[+] Pulling APK file(s) from device', max=len(apkpaths))
    verboseOutput = ""

    localapks = []
    for remotepath in apkpaths:
        baseapkname = remotepath.split('/')[-1]
        localapks.append(os.path.join(tmppath, pkgname + "-" + baseapkname))
        verboseOutput += f"[+] Pulled: {pkgname}-{baseapkname}\n"
        bar.next()
        # assertSubprocessSuccessfulRun(["adb", "pull", remotepath, localapks[-1]])
        assertSubprocessSuccessfulRun(["adb", "pull", remotepath, localapks[-1]] )
    
    bar.finish()
    verbosePrint(verboseOutput.rstrip())

    # Return the target APK path
    if len(localapks) == 1:
        return localapks[0]
    else:
        # Combine split APKs
        return combineSplitAPKs(pkgname, localapks, tmppath, disableStylesHack, extract_only)

def verbosePrint(msg):
    if getArgs().verbose:
        for line in msg.split("\n"):
            print(colored("    " + line, "light_grey"))

####################
# Combine app bundles/split APKs into a single APK for patching.
####################
def combineSplitAPKs(pkgname, localapks, tmppath, disableStylesHack, extract_only):
    warningPrint("\n[!] App bundle/split APK detected, rebuilding as a single APK.")
    
    # Extract the individual APKs
    baseapkdir = os.path.join(tmppath, pkgname + "-base")
    baseapkfilename = pkgname + "-base.apk"
    splitapkpaths = []

    print("")
    bar = Bar('[+] Disassembling split APKs', max=len(localapks))
    verboseOutput = ""
    
    for apkpath in localapks:
        verboseOutput += "\nExtracted: " + apkpath
        bar.next()
        apkdir = apkpath[:-4]
        ret = runApkTool(["d", apkpath, "-o", apkdir])
        if ret.returncode != 0:
            abort("\nError: Failed to run 'apktool d " + apkpath + " -o " + apkdir + "'.\nRun with --debug-output for more information.")
        
        # Record the destination paths of all but the base APK
        if not apkpath.endswith("base.apk"):
            splitapkpaths.append(apkdir)
        
        # Check for ProGuard/AndResGuard - this might b0rk decompile/recompile
        if detectProGuard(apkdir):
            warningPrint("\n[!] WARNING: Detected ProGuard/AndResGuard, decompile/recompile may not succeed.\n")
    
    bar.finish()

    verbosePrint(verboseOutput)

    # Walk the extracted APK directories and copy files and directories to the base APK
    print("\n[+] Rebuilding as a single APK")
    copySplitApkFiles(baseapkdir, splitapkpaths)
    
    # Fix public resource identifiers
    fixPublicResourceIDs(baseapkdir, splitapkpaths)
    
    # Hack: Delete duplicate style resource entries.
    if not disableStylesHack:
        hackRemoveDuplicateStyleEntries(baseapkdir)
    
    #Disable APK splitting in the base AndroidManifest.xml file
    disableApkSplitting(baseapkdir)

    # Fix apktool bug where ampersands are improperly escaped: https://github.com/iBotPeaches/Apktool/issues/2703
    verbosePrint("[+] Fixing any improperly escaped ampersands.")
    rawREReplace(os.path.join(baseapkdir, "res", "values", "strings.xml"), r'(&amp)([^;])', r'\1;\2')
    
    # Rebuild the base APK
    build(baseapkdir)
    
    # Return the new APK path
    return os.path.join(baseapkdir, "dist", baseapkfilename)
   
    

####################
# Attempt to detect ProGuard/AndResGuard.
####################
def detectProGuard(extractedPath):
    if os.path.exists(os.path.join(extractedPath, "original", "META-INF", "proguard")):
        return True
    if os.path.exists(os.path.join(extractedPath, "original", "META-INF", "MANIFEST.MF")):
        fh = open(os.path.join(extractedPath, "original", "META-INF", "MANIFEST.MF"))
        d = fh.read()
        fh.close()
        if "proguard" in d.lower():
            return True
    return False

####################
# Copy files and directories from split APKs into the base APK directory.
####################
def copySplitApkFiles(baseapkdir, splitapkpaths):
    for apkdir in splitapkpaths:
        for (root, dirs, files) in os.walk(apkdir):
            # Skip the original files directory
            if not root.startswith(os.path.join(apkdir, "original")):
                # Create any missing directories
                for d in dirs:
                    # Translate directory path to base APK path and create the directory if it doesn't exist
                    p = baseapkdir + os.path.join(root, d)[len(apkdir):]
                    if not os.path.exists(p):
                        dbgPrint("[+] Creating directory in base APK: " + p[len(baseapkdir):])
                        os.mkdir(p)
                
                # Copy files into the base APK
                for f in files:
                    # Skip the AndroidManifest.xml and apktool.yml in the APK root directory
                    if apkdir == root and (f == "AndroidManifest.xml" or f == "apktool.yml"):
                        continue
                    
                    # Translate path to base APK
                    p = baseapkdir + os.path.join(root, f)[len(apkdir):]
                    
                    # Copy files into the base APK, except for XML files in the res directory
                    if f.lower().endswith(".xml") and p.startswith(os.path.join(baseapkdir, "res")):
                        continue
                    dbgPrint("[+] Moving file to base APK: " + p[len(baseapkdir):])
                    shutil.move(os.path.join(root, f), p)

####################
# Fix public resource identifiers that are shared across split APKs.
# Maps all APKTOOL_DUMMY_ resource IDs in the base APK to the proper resource names from the
# split APKs, then updates references in other resource files in the base APK to use proper
# resource names.
####################
def fixPublicResourceIDs(baseapkdir, splitapkpaths):
    # Bail if the base APK does not have a public.xml
    if not os.path.exists(os.path.join(baseapkdir, "res", "values", "public.xml")):
        return
    verbosePrint("\n[+] Found public.xml in the base APK, fixing resource identifiers across split APKs.")
    
    # Mappings of resource IDs and names
    idToDummyName = {}
    dummyNameToRealName = {}
    
    # Step 1) Find all resource IDs that apktool has assigned a name of APKTOOL_DUMMY_XXX to.
    #         Load these into the lookup tables ready to resolve the real resource names from
    #         the split APKs in step 2 below.
    baseXmlTree = xml.etree.ElementTree.parse(os.path.join(baseapkdir, "res", "values", "public.xml"))
    for el in baseXmlTree.getroot():
        if "name" in el.attrib and "id" in el.attrib:
            if el.attrib["name"].startswith("APKTOOL_DUMMY_") and el.attrib["name"] not in idToDummyName:
                idToDummyName[el.attrib["id"]] = el.attrib["name"]
                dummyNameToRealName[el.attrib["name"]] = None
    verbosePrint("[+] Resolving " + str(len(idToDummyName)) + " resource identifiers.")
    
    # Step 2) Parse the public.xml file from each split APK in search of resource IDs matching
    #         those loaded during step 1. Each match gives the true resource name allowing us to
    #         replace all APKTOOL_DUMMY_XXX resource names with the true resource names back in
    #         the base APK.
    found = 0
    for splitdir in splitapkpaths:
        if os.path.exists(os.path.join(splitdir, "res", "values", "public.xml")):
            tree = xml.etree.ElementTree.parse(os.path.join(splitdir, "res", "values", "public.xml"))
            for el in tree.getroot():
                if "name" in el.attrib and "id" in el.attrib:
                    if el.attrib["id"] in idToDummyName:
                        dummyNameToRealName[idToDummyName[el.attrib["id"]]] = el.attrib["name"]
                        found += 1
    verbosePrint("[+] Located " + str(found) + " true resource names.")
    
    # Step 3) Update the base APK to replace all APKTOOL_DUMMY_XXX resource names with the true
    #         resource name.
    updated = 0
    for el in baseXmlTree.getroot():
        if "name" in el.attrib and "id" in el.attrib:
            if el.attrib["name"] in dummyNameToRealName and dummyNameToRealName[el.attrib["name"]] is not None:
                el.attrib["name"] = dummyNameToRealName[el.attrib["name"]]
                updated += 1
    baseXmlTree.write(os.path.join(baseapkdir, "res", "values", "public.xml"), encoding="utf-8", xml_declaration=True)
    verbosePrint("[+] Updated " + str(updated) + " dummy resource names with true names in the base APK.")
    
    # Step 4) Find all references to APKTOOL_DUMMY_XXX resources within other XML resource files
    #         in the base APK and update them to refer to the true resource name.
    updated = 0
    for (root, dirs, files) in os.walk(os.path.join(baseapkdir, "res")):
        for f in files:
            if f.lower().endswith(".xml"):
                try:
                    # Load the XML
                    xmlPath = os.path.join(root, f)
                    dbgPrint("[~] Parsing " + xmlPath)
                    tree = xml.etree.ElementTree.parse(xmlPath)
                    
                    # Register the namespaces and get the prefix for the "android" namespace
                    namespaces = dict([node for _,node in xml.etree.ElementTree.iterparse(os.path.join(baseapkdir, "AndroidManifest.xml"), events=["start-ns"])])
                    for ns in namespaces:
                        xml.etree.ElementTree.register_namespace(ns, namespaces[ns])
                    ns = "{" + namespaces["android"] + "}"
                    
                    # Update references to APKTOOL_DUMMY_XXX resources
                    changed = False
                    for el in tree.iter():
                        # Check for references to APKTOOL_DUMMY_XXX resources in attributes of this element
                        for attr in el.attrib:
                            val = el.attrib[attr]
                            if val.startswith("@") and "/" in val and val.split("/")[1].startswith("APKTOOL_DUMMY_") and dummyNameToRealName[val.split("/")[1]] is not None:
                                el.attrib[attr] = val.split("/")[0] + "/" + dummyNameToRealName[val.split("/")[1]]
                                updated += 1
                                changed = True
                            elif val.startswith("APKTOOL_DUMMY_") and dummyNameToRealName[val] is not None:
                                el.attrib[attr] = dummyNameToRealName[val]
                                updated += 1
                                changed = True
                            
                            if changed:
                                dbgPrint("[~] Patching dummy apktool attribute \"" + attr + "\" value \"" + val + "\"" + (" -> \"" + el.attrib[attr] + "\"" if val != el.attrib[attr] else "") + " (" + str(updated) + ")")
                            
                            # Fix for untracked bug where drawables are decoded without drawable values (@null)
                            if f == "drawables.xml" and attr == "name" and el.text is None:
                                dbgPrint("[~] Patching null decoded drawable \"" + el.attrib[attr] + "\" (" + str(updated) + ")")
                                el.text = NULL_DECODED_DRAWABLE_COLOR
                        
                        # Check for references to APKTOOL_DUMMY_XXX resources in the element text
                        val = el.text
                        if val is not None and val.startswith("@") and "/" in val and val.split("/")[1].startswith("APKTOOL_DUMMY_") and dummyNameToRealName[val.split("/")[1]] is not None:
                            el.text = val.split("/")[0] + "/" + dummyNameToRealName[val.split("/")[1]]
                            updated += 1
                            changed = True
                            dbgPrint("[~] Patching dummy apktool element \"" + el.get('name', el.tag) + "\" value \"" + val + (" -> \"" + el.text + "\"" if val != el.text else "") + str(updated) + ")")
                    
                    # Save the file if it was updated
                    if changed:
                        dbgPrint("[+] Writing patched " + f)
                        tree.write(os.path.join(root, f), encoding="utf-8", xml_declaration=True)
                except xml.etree.ElementTree.ParseError:
                    print("[-] XML parse error in " + os.path.join(root, f) + ", skipping.")
    verbosePrint("[+] Updated " + str(updated) + " references to dummy resource names in the base APK.")

####################
# Hack to remove duplicate style resource entries before rebuilding.
# 
# Possibly a bug in apktool affecting the Uber app (com.ubercab)
# -> res/values/styles.xml has <style> elements where two child <item> elements had the same name e.g.
#        <item name="borderWarning">@color/ub__ui_core_v2_orange200</item>
#        <item name="borderWarning">@color/ub__ui_core_v2_orange400</item>
# --> Doing an "apktool d com.ubercab.apk" then "apktool b com.ubercab" fails, so not a bug with patch-apk.py.
# --> See: https://github.com/iBotPeaches/Apktool/issues/2240
# 
# This hack parses res/values/styles.xml, finds all offending elements, removes them, then saves the result.
####################
def hackRemoveDuplicateStyleEntries(baseapkdir):
    # Bail if there is no styles.xml
    if not os.path.exists(os.path.join(baseapkdir, "res", "values", "styles.xml")):
        return
    
    # Duplicates
    dupes = []
    
    # Parse styles.xml and find all <item> elements with duplicate names
    tree = xml.etree.ElementTree.parse(os.path.join(baseapkdir, "res", "values", "styles.xml"))
    for styleEl in tree.getroot().findall("style"):
        itemNames = []
        for itemEl in styleEl:
            if "name" in itemEl.attrib and itemEl.attrib["name"] in itemNames:
                dupes.append([styleEl, itemEl])
            else:
                itemNames.append(itemEl.attrib["name"])
    
    # Delete all duplicates from the tree
    for dupe in dupes:
        dupe[0].remove(dupe[1])
    
    # Save the result if any duplicates were found and removed
    if len(dupes) > 0:
        verbosePrint("\n[+] Found styles.xml in the base APK, checking for duplicate <style> -> <item> elements and removing.")
        warningPrint("[!] Warning: this is a complete hack and may impact the visuals of the app, disable with --disable-styles-hack.")
        tree.write(os.path.join(baseapkdir, "res", "values", "styles.xml"), encoding="utf-8", xml_declaration=True)
        print("[+] Removed " + str(len(dupes)) + " duplicate entries from styles.xml.")

####################
# Update AndroidManifest.xml to disable APK splitting.
# -> Removes the "isSplitRequired" attribute of the "application" element.
# -> Sets the "extractNativeLibs" attribute of the "application" element.
# -> Removes meta-data elements with the name "com.android.vending.splits" or "com.android.vending.splits.required"
####################
def disableApkSplitting(baseapkdir):
    verbosePrint("[+] Disabling APK splitting in AndroidManifest.xml of base APK.")
    
    # Load AndroidManifest.xml
    tree = xml.etree.ElementTree.parse(os.path.join(baseapkdir, "AndroidManifest.xml"))
    
    # Register the namespaces and get the prefix for the "android" namespace
    namespaces = dict([node for _,node in xml.etree.ElementTree.iterparse(os.path.join(baseapkdir, "AndroidManifest.xml"), events=["start-ns"])])
    for ns in namespaces:
        xml.etree.ElementTree.register_namespace(ns, namespaces[ns])
    ns = "{" + namespaces["android"] + "}"
    
    # Disable APK splitting
    appEl = None
    elsToRemove = []
    for el in tree.iter():
        if el.tag == "application":
            appEl = el
            if ns + "isSplitRequired" in el.attrib:
                del el.attrib[ns + "isSplitRequired"]
            if ns + "extractNativeLibs" in el.attrib:
                el.attrib[ns + "extractNativeLibs"] = "true"
        elif appEl is not None and el.tag == "meta-data":
            if ns + "name" in el.attrib:
                if el.attrib[ns + "name"] == "com.android.vending.splits.required":
                    elsToRemove.append(el)
                elif el.attrib[ns + "name"] == "com.android.vending.splits":
                    elsToRemove.append(el)
    for el in elsToRemove:
        appEl.remove(el)
    
    # Save the updated AndroidManifest.xml
    tree.write(os.path.join(baseapkdir, "AndroidManifest.xml"), encoding="utf-8", xml_declaration=True)

####################
# Replace occurrences of a pattern in a file with a replacement pattern or function (a la re.sub)
####################
def rawREReplace(path, pattern, replacement):
    if os.path.exists(path):
        contents = ""
        with open(path, 'r') as file:
            contents = file.read()
        newContents = re.sub(pattern, replacement, contents)
        if (contents != newContents):
            dbgPrint("\n[~] Patching " + path)
            with open(path, 'w') as file:
                file.write(newContents)
    else:
        abort("\nError: Failed to find file at " + path + " for pattern replacement")

####################
# Patch an APK to enable support for user-installed CA certs (e.g. Burp Suite CA cert).
####################
def enableUserCerts(apkfile):
    # Create a separate temp directory to work from
    print("\n[+] Patching APK to enable support for user-installed CA certificates.")
    with tempfile.TemporaryDirectory() as tmppath:
        # Extract the APK
        apkdir = os.path.join(tmppath, apkfile.split(os.sep)[-1][:-4])
        apkname = apkdir.split(os.sep)[-1] + ".apk"
        ret = runApkTool(["d", apkfile, "-o", apkdir])
        if ret.returncode != 0:
            abort("Error: Failed to run 'apktool d " + apkfile + " -o " + apkdir + "'.\nRun with --debug-output for more information.")
        
        # Load AndroidManifest.xml and check for or create the networkSecurityConfig attribute
        tree = xml.etree.ElementTree.parse(os.path.join(apkdir, "AndroidManifest.xml"))
        namespaces = dict([node for _,node in xml.etree.ElementTree.iterparse(os.path.join(apkdir, "AndroidManifest.xml"), events=["start-ns"])])
        for ns in namespaces:
            xml.etree.ElementTree.register_namespace(ns, namespaces[ns])
        ns = "{" + namespaces["android"] + "}"
        for el in tree.findall("application"):
            el.attrib[ns + "networkSecurityConfig"] = "@xml/network_security_config"
        tree.write(os.path.join(apkdir, "AndroidManifest.xml"), encoding="utf-8", xml_declaration=True)
        
        # Create a network security config file
        fh = open(os.path.join(apkdir, "res", "xml", "network_security_config.xml"), "wb")
        fh.write("<?xml version=\"1.0\" encoding=\"utf-8\" ?><network-security-config><base-config><trust-anchors><certificates src=\"system\" /><certificates src=\"user\" /></trust-anchors></base-config></network-security-config>".encode("utf-8"))
        fh.close()
        
        # Rebuild and sign the APK
        build(apkdir) # Fix https://github.com/NickstaDB/patch-apk/issues/30
        signAndZipAlign(apkdir, apkname)

####################
# Main
####################
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit()

