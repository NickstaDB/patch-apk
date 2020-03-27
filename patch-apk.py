#!/usr/bin/python3
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree

####################
# Main()
####################
def main():
	#Check that dependencies are available
	checkDependencies()
	
	#Grab argz
	args = getArgs()
	
	#Verify the package name and ensure it's installed (also supports partial package names)
	pkgname = verifyPackageName(args.pkgname)
	
	#Get the APK path(s) from the device
	apkpaths = getAPKPathsForPackage(pkgname)
	
	#Create a temp directory to work from
	with tempfile.TemporaryDirectory() as tmppath:
		#Get the APK to patch. Combine app bundles/split APKs into a single APK.
		apkfile = getTargetAPK(pkgname, apkpaths, tmppath)
		
		#Patch the target APK with objection
		print("Patching " + apkfile.split(os.sep)[-1] + " with objection.")
		subprocess.run(["objection", "patchapk", "--skip-resources", "-s", apkfile], stdout=subprocess.DEVNULL)
		os.remove(apkfile)
		shutil.move(apkfile[:-4] + ".objection.apk", apkfile)
		print("")
		
		#Enable support for user-installed CA certs (e.g. Burp Suite CA installed on device by user)
		if args.no_enable_user_certs == False:
			enableUserCerts(apkfile)
		
		#Uninstall the original package from the device
		print("Uninstalling the original package from the device.")
		subprocess.run(["adb", "uninstall", pkgname], stdout=subprocess.DEVNULL)
		print("")
		
		#Install the patched APK
		print("Installing the patched APK to the device.")
		subprocess.run(["adb", "install", apkfile], stdout=subprocess.DEVNULL)
		print("")
		
		#Done
		print("Done, cleaning up temporary files.")

####################
# Check that required dependencies are present:
# -> Tools used
# -> Android device connected
####################
def checkDependencies():
	deps = ["adb", "apktool", "jarsigner", "objection", "zipalign"]
	missing = []
	for dep in deps:
		if shutil.which(dep) is None:
			missing.append(dep)
	if len(missing) > 0:
		print("Error, missing dependencies, ensure the following commands are available on the PATH: " + (", ".join(missing)))
		sys.exit(1)
	
	#Verify that an Android device is connected
	proc = subprocess.run(["adb", "devices"], stdout=subprocess.PIPE)
	deviceOut = proc.stdout.decode("utf-8")
	if len(deviceOut.strip().split(os.linesep)) == 1:
		print("Error, no Android device connected (\"adb devices\"), connect a device first.")
		sys.exit(1)

####################
# Grab command line parameters
####################
def getArgs():
	parser = argparse.ArgumentParser(
		description="patch-apk - Pull and patch Android apps for use with objection/frida."
	)
	parser.add_argument("--no-enable-user-certs", help="Prevent patch-apk from enabling user-installed certificate support via network security config in the patched APK.", action="store_true")
	parser.add_argument("pkgname", help="The name, or partial name, of the package to patch (e.g. com.foo.bar).")
	return parser.parse_args()

####################
# Verify the package name - checks whether the target package is installed
# on the device or if an exact match is not found presents the options to
# the user for selection.
####################
def verifyPackageName(pkgname):
	#Get a list of installed packages matching the given name
	packages = []
	proc = subprocess.run(["adb", "shell", "pm", "list", "packages"], stdout=subprocess.PIPE)
	out = proc.stdout.decode("utf-8")
	for line in out.split(os.linesep):
		if line.startswith("package:"):
			line = line[8:]
			if pkgname.lower() in line.lower():
				packages.append(line)
	
	#Bail out if no matching packages were found
	if len(packages) == 0:
		print("Error, no packages found on the device matching the search term '" + pkgname + "'.")
		print("Run 'adb shell pm list packages' to verify installed package names.")
		sys.exit(1)
	
	#Return the target package name, offering a choice to the user if necessary
	if len(packages) == 1:
		return packages[0]
	else:
		print("Multiple matching packages installed, select the package to patch.")
		choice = -1
		while choice == -1:
			for i in range(len(packages)):
				print("[" + str(i + 1) + "] " + packages[i])
			choice = input("Choice: ")
			if choice.isnumeric() == False or int(choice) < 1 or int(choice) > len(packages):
				print("Invalid choice.\n")
				choice = -1
		print("")
		return packages[int(choice) - 1]

####################
# Get the APK path(s) on the device for the given package name.
####################
def getAPKPathsForPackage(pkgname):
	print("Getting APK path(s) for package: " + pkgname)
	paths = []
	proc = subprocess.run(["adb", "shell", "pm", "path", pkgname], stdout=subprocess.PIPE)
	out = proc.stdout.decode("utf-8")
	for line in out.split(os.linesep):
		if line.startswith("package:"):
			print("[+] APK path: " + line[8:])
			paths.append(line[8:])
	print("")
	return paths

####################
# Pull the APK file(s) for the package and return the local file path to work with.
# If the package is an app bundle/split APK, combine the APKs into a single APK.
####################
def getTargetAPK(pkgname, apkpaths, tmppath):
	#Pull the APKs from the device
	print("Pulling APK file(s) from device.")
	localapks = []
	for remotepath in apkpaths:
		baseapkname = remotepath.split(os.sep)[-1]
		localapks.append(os.path.join(tmppath, pkgname + "-" + baseapkname))
		print("[+] Pulling: " + pkgname + "-" + baseapkname)
		subprocess.run(["adb", "pull", remotepath, localapks[-1]], stdout=subprocess.DEVNULL)
	print("")
	
	#Return the target APK path
	if len(localapks) == 1:
		return localapks[0]
	else:
		#Combine split APKs
		return combineSplitAPKs(pkgname, localapks, tmppath)

####################
# Combine app bundles/split APKs into a single APK for patching.
####################
def combineSplitAPKs(pkgname, localapks, tmppath):
	print("App bundle/split APK detected, rebuilding as a single APK.")
	print("")
	
	#Extract the individual APKs
	print("Extracting individual APKs with apktool.")
	baseapkdir = os.path.join(tmppath, pkgname + "-base")
	baseapkfilename = pkgname + "-base.apk"
	splitapkpaths = []
	for apkpath in localapks:
		print("[+] Extracting: " + apkpath)
		apkdir = apkpath[:-4]
		subprocess.run(["apktool", "d", apkpath, "-o", apkdir], stdout=subprocess.DEVNULL)
		
		#Record the destination paths of all but the base APK
		if apkpath.endswith("base.apk") == False:
			splitapkpaths.append(apkdir)
	print("")
	
	#Walk the extracted APK directories and copy files and directories to the base APK
	copySplitApkFiles(baseapkdir, splitapkpaths)
	
	#Fix public resource identifiers
	fixPublicResourceIDs(baseapkdir, splitapkpaths)
	
	#Disable APK splitting in the base AndroidManifest.xml file
	disableApkSplitting(baseapkdir)
	
	#Rebuild the base APK
	print("Rebuilding as a single APK.")
	print("[+] Building APK with apktool.")
	subprocess.run(["apktool", "b", baseapkdir], stdout=subprocess.DEVNULL)
	
	#Sign the new APK
	print("[+] Signing new APK.")
	subprocess.run([
			"jarsigner", "-sigalg", "SHA1withRSA", "-digestalg", "SHA1", "-keystore",
			os.path.realpath(os.path.join(os.path.realpath(__file__), "..", "data", "patch-apk.keystore")),
			"-storepass", "patch-apk", os.path.join(baseapkdir, "dist", baseapkfilename), "patch-apk-key"],
		stdout=subprocess.DEVNULL
	)
	
	#Zip align the new APK
	print("[+] Zip aligning new APK.")
	subprocess.run([
			"zipalign", "-f", "4", os.path.join(baseapkdir, "dist", baseapkfilename),
			os.path.join(baseapkdir, "dist", baseapkfilename[:-4] + "-aligned.apk")
		],
		stdout=subprocess.DEVNULL
	)
	shutil.move(os.path.join(baseapkdir, "dist", baseapkfilename[:-4] + "-aligned.apk"), os.path.join(baseapkdir, "dist", baseapkfilename))
	print("")
	
	#Return the new APK path
	return os.path.join(baseapkdir, "dist", baseapkfilename)

####################
# Copy files and directories from split APKs into the base APK directory.
####################
def copySplitApkFiles(baseapkdir, splitapkpaths):
	print("Copying files and directories from split APKs into base APK.")
	for apkdir in splitapkpaths:
		for (root, dirs, files) in os.walk(apkdir):
			#Skip the original files directory
			if root.startswith(os.path.join(apkdir, "original")) == False:
				#Create any missing directories
				for d in dirs:
					#Translate directory path to base APK path and create the directory if it doesn't exist
					p = baseapkdir + os.path.join(root, d)[len(apkdir):]
					if os.path.exists(p) == False:
						print("[+] Creating directory in base APK: " + p[len(baseapkdir):])
						os.mkdir(p)
				
				#Copy files into the base APK
				for f in files:
					#Skip the AndroidManifest.xml and apktool.yml in the APK root directory
					if apkdir == root and (f == "AndroidManifest.xml" or f == "apktool.yml"):
						continue
					
					#Translate path to base APK
					p = baseapkdir + os.path.join(root, f)[len(apkdir):]
					
					#Copy files into the base APK, except for XML files in the res directory
					if f.lower().endswith(".xml") and p.startswith(os.path.join(baseapkdir, "res")):
						continue
					print("[+] Moving file to base APK: " + p[len(baseapkdir):])
					shutil.move(os.path.join(root, f), p)
	print("")

####################
# Fix public resource identifiers that are shared across split APKs.
# Maps all APKTOOL_DUMMY_ resource IDs in the base APK to the proper resource names from the
# split APKs, then updates references in other resource files in the base APK to use proper
# resource names.
####################
def fixPublicResourceIDs(baseapkdir, splitapkpaths):
	#Bail if the base APK does not have a public.xml
	if os.path.exists(os.path.join(baseapkdir, "res", "values", "public.xml")) == False:
		return
	print("Found public.xml in the base APK, fixing resource identifiers across split APKs.")
	
	#Mappings of resource IDs and names
	idToDummyName = {}
	dummyNameToRealName = {}
	
	#Step 1) Find all resource IDs that apktool has assigned a name of APKTOOL_DUMMY_XXX to.
	#        Load these into the lookup tables ready to resolve the real resource names from
	#        the split APKs in step 2 below.
	baseXmlTree = xml.etree.ElementTree.parse(os.path.join(baseapkdir, "res", "values", "public.xml"))
	for el in baseXmlTree.getroot().getchildren():
		if "name" in el.attrib and "id" in el.attrib:
			if el.attrib["name"].startswith("APKTOOL_DUMMY_") and el.attrib["name"] not in idToDummyName:
				idToDummyName[el.attrib["id"]] = el.attrib["name"]
				dummyNameToRealName[el.attrib["name"]] = ""
	print("[+] Resolving " + str(len(idToDummyName)) + " resource identifiers.")
	
	#Step 2) Parse the public.xml file from each split APK in search of resource IDs matching
	#        those loaded during step 1. Each match gives the true resource name allowing us to
	#        replace all APKTOOL_DUMMY_XXX resource names with the true resource names back in
	#        the base APK.
	found = 0
	for splitdir in splitapkpaths:
		if os.path.exists(os.path.join(splitdir, "res", "values", "public.xml")):
			tree = xml.etree.ElementTree.parse(os.path.join(splitdir, "res", "values", "public.xml"))
			for el in tree.getroot().getchildren():
				if "name" in el.attrib and "id" in el.attrib:
					if el.attrib["id"] in idToDummyName:
						dummyNameToRealName[idToDummyName[el.attrib["id"]]] = el.attrib["name"]
						found += 1
	print("[+] Located " + str(found) + " true resource names.")
	
	#Step 3) Update the base APK to replace all APKTOOL_DUMMY_XXX resource names with the true
	#        resource name.
	updated = 0
	for el in baseXmlTree.getroot().getchildren():
		if "name" in el.attrib and "id" in el.attrib:
			if el.attrib["name"] in dummyNameToRealName:
				el.attrib["name"] = dummyNameToRealName[el.attrib["name"]]
				updated += 1
	baseXmlTree.write(os.path.join(baseapkdir, "res", "values", "public.xml"), encoding="utf-8", xml_declaration=True)
	print("[+] Updated " + str(updated) + " dummy resource names with true names in the base APK.")
	
	#Step 4) Find all references to APKTOOL_DUMMY_XXX resources within other XML resource files
	#        in the base APK and update them to refer to the true resource name.
	updated = 0
	for (root, dirs, files) in os.walk(os.path.join(baseapkdir, "res")):
		for f in files:
			if f.lower().endswith(".xml"):
				#Load the XML
				tree = xml.etree.ElementTree.parse(os.path.join(root, f))
				
				#Register the namespaces and get the prefix for the "android" namespace
				namespaces = dict([node for _,node in xml.etree.ElementTree.iterparse(os.path.join(baseapkdir, "AndroidManifest.xml"), events=["start-ns"])])
				for ns in namespaces:
					xml.etree.ElementTree.register_namespace(ns, namespaces[ns])
				ns = "{" + namespaces["android"] + "}"
				
				#Update references to APKTOOL_DUMMY_XXX resources
				changed = False
				for el in tree.iter():
					#Check for references to APKTOOL_DUMMY_XXX resources in attributes of this element
					for attr in el.attrib:
						val = el.attrib[attr]
						if val.startswith("@") and "/" in val and val.split("/")[1].startswith("APKTOOL_DUMMY_"):
							el.attrib[attr] = val.split("/")[0] + "/" + dummyNameToRealName[val.split("/")[1]]
							updated += 1
							changed = True
						elif val.startswith("APKTOOL_DUMMY_"):
							el.attrib[attr] = dummyNameToRealName[val]
							updated += 1
							changed = True
					
					#Check for references to APKTOOL_DUMMY_XXX resources in the element text
					val = el.text
					if val is not None and val.startswith("@") and "/" in val and val.split("/")[1].startswith("APKTOOL_DUMMY_"):
						el.text = val.split("/")[0] + "/" + dummyNameToRealName[val.split("/")[1]]
						updated += 1
						changed = True
				
				#Save the file if it was updated
				if changed == True:
					tree.write(os.path.join(root, f), encoding="utf-8", xml_declaration=True)
	print("[+] Updated " + str(updated) + " references to dummy resource names in the base APK.")
	print("")

####################
# Update AndroidManifest.xml to disable APK splitting.
# -> Removes the "isSplitRequired" attribute of the "application" element.
# -> Sets the "extractNativeLibs" attribute of the "application" element.
# -> Removes meta-data elements with the name "com.android.vending.splits" or "com.android.vending.splits.required"
####################
def disableApkSplitting(baseapkdir):
	print("Disabling APK splitting in AndroidManifest.xml of base APK.")
	
	#Load AndroidManifest.xml
	tree = xml.etree.ElementTree.parse(os.path.join(baseapkdir, "AndroidManifest.xml"))
	
	#Register the namespaces and get the prefix for the "android" namespace
	namespaces = dict([node for _,node in xml.etree.ElementTree.iterparse(os.path.join(baseapkdir, "AndroidManifest.xml"), events=["start-ns"])])
	for ns in namespaces:
		xml.etree.ElementTree.register_namespace(ns, namespaces[ns])
	ns = "{" + namespaces["android"] + "}"
	
	#Disable APK splitting
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
	
	#Save the updated AndroidManifest.xml
	tree.write(os.path.join(baseapkdir, "AndroidManifest.xml"), encoding="utf-8", xml_declaration=True)
	print("")

####################
# Patch an APK to enable support for user-installed CA certs (e.g. Burp Suite CA cert).
####################
def enableUserCerts(apkfile):
	#Create a separate temp directory to work from
	print("Patching APK to enable support for user-installed CA certificates.")
	with tempfile.TemporaryDirectory() as tmppath:
		#Extract the APK
		apkdir = os.path.join(tmppath, apkfile.split(os.sep)[-1][:-4])
		apkname = apkdir.split(os.sep)[-1] + ".apk"
		subprocess.run(["apktool", "d", apkfile, "-o", apkdir], stdout=subprocess.DEVNULL)
		
		#Load AndroidManifest.xml and check for or create the networkSecurityConfig attribute
		tree = xml.etree.ElementTree.parse(os.path.join(apkdir, "AndroidManifest.xml"))
		namespaces = dict([node for _,node in xml.etree.ElementTree.iterparse(os.path.join(apkdir, "AndroidManifest.xml"), events=["start-ns"])])
		for ns in namespaces:
			xml.etree.ElementTree.register_namespace(ns, namespaces[ns])
		ns = "{" + namespaces["android"] + "}"
		for el in tree.findall("application"):
			el.attrib[ns + "networkSecurityConfig"] = "@xml/network_security_config"
		tree.write(os.path.join(apkdir, "AndroidManifest.xml"), encoding="utf-8", xml_declaration=True)
		
		#Create a network security config file
		fh = open(os.path.join(apkdir, "res", "xml", "network_security_config.xml"), "wb")
		fh.write("<?xml version=\"1.0\" encoding=\"utf-8\" ?><network-security-config><base-config><trust-anchors><certificates src=\"user\" /></trust-anchors></base-config></network-security-config>".encode("utf-8"))
		fh.close()
		
		#Rebuild and sign the APK
		subprocess.run(["apktool", "b", apkdir], stdout=subprocess.DEVNULL)
		subprocess.run([
				"jarsigner", "-sigalg", "SHA1withRSA", "-digestalg", "SHA1", "-keystore",
				os.path.realpath(os.path.join(os.path.realpath(__file__), "..", "data", "patch-apk.keystore")),
				"-storepass", "patch-apk", os.path.join(apkdir, "dist", apkname), "patch-apk-key"],
			stdout=subprocess.DEVNULL
		)
		
		#Zip align the new APK
		os.remove(apkfile)
		subprocess.run(["zipalign", "4", os.path.join(apkdir, "dist", apkname), apkfile], stdout=subprocess.DEVNULL)
	print("")

####################
# Main
####################
if __name__ == "__main__":
	main()
