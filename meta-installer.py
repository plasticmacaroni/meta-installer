from unicodedata import ucd_3_2_0
import PySimpleGUI as sg
import os
import urllib
from urllib.request import urlopen
import shutil
import pathlib
import requests
import zipfile_deflate64 as zipfile
from ctypes import windll
import yaml
from bs4 import BeautifulSoup
import sys
import winreg
import vdf
import usvfs
from elevate import elevate
import time

class ModPicker:
    def __init__(self):

        layout = [[]]

        for folder in os.listdir("meta-installer-config"):
            with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "meta-installer-config", folder, 'install.yaml'), 'r') as file:
                configuration = yaml.safe_load(file)
                # layout[0].append([sg.Image(image_source=os.path.join("meta-installer-config", folder, 'banner.png'), size=(150,80), expand_x=True)])
                layout[0].extend([[sg.Button(configuration["default_config"]["virtual_game_folder"], image_source=os.path.join("meta-installer-config", folder, 'banner.png'), key=folder, font=("Any", 20), image_size=(800, 150))]])

        # layout[0].append([sg.Text(size=(15, 1), font=('Helvetica', 18), text_color='red', key='out')])

        self.window = sg.Window('Mod Selector', layout)
    
    def run(self):
        while (True):

            # pysimplegui context and event loop
            event, values = self.window.read(timeout=100) 
            if event in (sg.WIN_CLOSED, 'Exit'):
                print("quitting!") 
                break

            if event == sg.WIN_CLOSED or event == 'Exit':
                break

            if event != "__TIMEOUT__":
                must_elevate = False
                # print(event, values, os.path.join("meta-installer-config", event, "install.yaml"))
                # this is gross -- why should installers require admin? recommend reaching out to installer creators and recommending admin is not used...
                with open(os.path.join("meta-installer-config", event, "install.yaml"), 'r') as file:
                    configuration = yaml.safe_load(file)
                    # for index, action_list in enumerate(self.install_config["install_steps"]):
                    for index, actionlist in enumerate(configuration["install_steps"]):
                        for key, value in actionlist.items():
                            if type(value) is dict:
                                if "use_symlinks" in value.keys():
                                    must_elevate = True
                self.window.close()
                return (os.path.join("meta-installer-config", event, "install.yaml")), must_elevate

            # for value in values:
            #     print("quitting!") 
            #     print(value)

        self.window.close()


        # Loop forever reading the window's values, updating the Input field
        keys_entered = ''
        while True:
            event, values = self.window.read()  # read the window
            if event == sg.WIN_CLOSED:  # if the X button clicked, just exit
                break
            if event == 'Clear':  # clear keys if clear button
                keys_entered = ''
            elif event in '1234567890':
                keys_entered = values['input']  # get what's been entered so far
                keys_entered += event  # add the new digit
            elif event == 'Submit':
                keys_entered = values['input']
                self.window['out'].update(keys_entered)  # output the final string

            self.window['input'].update(keys_entered)  # change the window to reflect current key string   

class Downloader:
    def __init__(self, install_config_location):

        # Tracks steps
        self.index = 1
        # metadata
        self.has_run = False
        self.found_steam_installation = False
        # Config object
        self.vfs = None
        # Build window
        # sg.theme('DarkAmber')
        sg.LOOK_AND_FEEL_TABLE['InstallerTheme'] = {'BACKGROUND': '#020202',
            'TEXT': '#B49759',
            'INPUT': '#B49759',
            'TEXT_INPUT': '#000000',
            'SCROLL': '#B49759',
            'BUTTON': ('#020202', '#B49759'),
            'PROGRESS': ('#020202', '#B49759'),
            'BORDER': 1, 'SLIDER_DEPTH': 0,
            'PROGRESS_DEPTH': 0, }
        sg.theme("InstallerTheme")

        # Start with no message displayed, as it's likely the script will display a message instantly
        self.main_message = ""
        self.step = ""
        layout = [
            [sg.Image(os.path.join(os.path.dirname(install_config_location), "banner.png"), size=(150,80), expand_x=True)],
            [sg.Text(self.step, size=(None, None), font='ANY 42', key="STEP", pad=(20, 30))], 
            [sg.HorizontalSeparator()],
            [sg.Text(self.main_message, size=(60, None), font = "ANY 20", key="MAIN_MESSAGE", pad=(40, 40))], 
            [
                sg.Button("NEXT", key="OK", font='ANY 20', size=(10, None))
            ]
        ]
        # Create the window
        self.window = sg.Window("Easy Installer", default_element_size=(20, 1), layout=layout, element_justification='c', icon=os.path.join(os.path.dirname(install_config_location), "exe-icon.ico"), enable_close_attempted_event=True)
        # Load install.yaml config
        with open(install_config_location, 'r') as file:
            install_config = yaml.safe_load(file)
        self.install_config = install_config

    def set_message(self, message):
        #update the step while we're at it
        step = self.index
        if step == 0: 
            step = 1
        self.step = "Step " + str(step) + " of " + str(len(self.install_config["install_steps"])-1)
        self.window.Element("STEP").update(self.step)
        #update the message
        self.window.Element("MAIN_MESSAGE").update(message)
        event, values = self.window.read()
        if event in (sg.WIN_CLOSE_ATTEMPTED_EVENT, sg.WIN_CLOSED, 'Exit', None):
            print("quitting!") 
            sys.exit()

    def check_size(self, url, local_file):
        url = self.find_moddb_download(url)
        headers = {
            "User-Agent": self.install_config["default_config"]["user_agent"]
        }
        content_length = requests.get(url, headers=headers, stream=True).headers['Content-length']
        # change directory to the mod folder
        # os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"]))
        if int(content_length) != os.stat(local_file).st_size:
            self.set_message("File size unmatch for " + local_file + " from " + url + "\n" + content_length + " online vs. " + str(os.stat(local_file).st_size) + " locally.")
            return False
        return True

    def download_file(self, url, local_filename):
        print(local_filename)
        # exit()
        # first use moddb workaround for relevant files
        url = self.find_moddb_download(url)
        headers = {
            "User-Agent": self.install_config["default_config"]["user_agent"],
        }
        content_length = requests.get(url, headers=headers, stream=True).headers['Content-length']
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status()
            dir = os.path.dirname(local_filename)
            # create directory if it does not exist
            if not os.path.exists(dir):
                os.makedirs(dir)

            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
                    i = os.path.getsize(local_filename)
                    ret_flag = sg.OneLineProgressMeter(local_filename + " Download", i+1, int(content_length), 'Download initiated.', 'Transferring data through hyper-relays.', grab_anywhere=True)
                    if ret_flag == False or sg.WIN_CLOSED:
                        self.set_message("Download cancelled. Press Next to restart download.")
            sg.OneLineProgressMeter(local_filename + " download progress...", int(content_length), int(content_length)) # call function with current == max value to instantly close
        return local_filename

    # this should probably somehow be definable per site in the install.yaml file, not in code
    def find_moddb_download(self, url):
        if "moddb" in url:
            try:
                page = requests.get(url)
                soup = BeautifulSoup(page.content, "html.parser")
                results = urllib.parse.urljoin("https://moddb.com", soup.find(id="downloadmirrorstoggle").attrs["href"])
                page = requests.get(results)
                soup = BeautifulSoup(page.content, "html.parser")
                results = urllib.parse.urljoin("https://moddb.com", soup.find("a").attrs["href"])
                url = results
                return url
            except Exception:
                print(Exception)
                sys.exit()
        return url
    
    def set_up_vfs(self):
        # Define a virtual directory link rule 
        # Get the directory of the current script 
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # The full path of the mod folder
        local_mod_folder_path = os.path.join(current_dir, "modpacks", self.install_config["default_config"]["virtual_game_folder"])
        # Create the new folder if it doesn't exist
        if not os.path.exists(local_mod_folder_path):
            os.makedirs(local_mod_folder_path)

        print("Pointed", local_mod_folder_path, "to", self.install_config["confirmed_install"])
        vdir = usvfs.VirtualDirectory(self.install_config["confirmed_install"], local_mod_folder_path)  # If a process running in the vfs tries to access dest/*, it'll be redirected to src/*
        vdir2 = usvfs.VirtualDirectory(local_mod_folder_path, self.install_config["confirmed_install"])  # If a process running in the vfs tries to access dest/*, it'll be redirected to src/*

        # Define our vfs layout
        vfs_map = usvfs.Mapping()    # Create a vfs mapping. This is a collection 
                                     # of virtual link rules that can be applied to the vfs
        vfs_map.link(vdir)           # Add any VirtualDirectory and/or VirtualFile rules like this
        vfs_map.link(vdir2)

        # Set up the vfs
        vfs = usvfs.UserspaceVFS()   # Create a usvfs controller with default instance name and configuration
        vfs.initialize()             # Initialize it
        vfs.set_mapping(vfs_map)     # Apply mapping
        return vfs
    
    def find_steam_installation(self):
        if self.install_config["default_config"]["steam_setup"] == True:
            try:
                hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\WOW6432Node\Valve\Steam")
            except:
                hkey = None
                print(sys.exc_info())
                sys.exit()
        else: 
            self.found_steam_installation = True
        steam_paths = winreg.QueryValueEx(hkey, "InstallPath")
        winreg.CloseKey(hkey)
        d = vdf.load(open(steam_paths[0] + "/steamapps/libraryfolders.vdf"))
        installation_paths = []
        for num in d["libraryfolders"]:
            installation_paths.append(d["libraryfolders"][num]["path"])
        self.install_config["installation_paths"] = installation_paths
        for installation_path in self.install_config["installation_paths"]:
            try: 
                ret = os.path.exists(installation_path + "/steamapps/common/" + self.install_config["default_config"]["game_folder"])
                if ret == True:
                    self.install_config["confirmed_install"] = installation_path + "/steamapps/common/" + self.install_config["default_config"]["game_folder"]
                    # self.set_message("Found the Steam installation directory at:\n\n" + self.install_config["confirmed_install"])
            except Exception as e:
                print(e)
                sys.exit()
        if len(self.install_config["installation_paths"]) == 0:
            print("Could not find Steam installation directory. You could always disable Steam detection in settings if you're not using Steam.")
            self.set_message("Could not find Steam installation directory. You could always disable Steam detection in settings if you're not using Steam.")
            sys.exit()
        else:
            # os.chdir(self.install_config["confirmed_install"])
            pass

    def is_file_in_directory(self, directory, file_name):
        print("Directory", directory)
        for file in os.listdir(directory):
            if file.endswith(file_name):
                return True
        return False

    def is_extension_in_directory(self, directory, extension):
        for file in os.listdir(directory):
            if file.endswith(extension):
                return True
        return False

    def run(self):
        while (True):
            # pysimplegui context and event loop
            event, values = self.window.read(timeout=100) 
            if event in (sg.WIN_CLOSED, 'Exit'):
                print("quitting!") 
                break

            # break if we're done running the loop
            if self.has_run and event == "OK":
                break

            # get Steam info and detect game folder if it's a Steam game
            if not self.found_steam_installation:
                self.find_steam_installation()
                print("Found install at:", self.install_config["confirmed_install"])
                self.found_steam_installation == True

            # Set up VFS
            if self.install_config["confirmed_install"] != "":
                self.vfs = self.set_up_vfs()
            if self.vfs == None:
                print("Error setting up vfs...")
                exit()

            # go through each install.yaml install_steps action
            if not self.has_run:
                for index, action_list in enumerate(self.install_config["install_steps"]):
                    # update index (how progress is tracked)
                    self.index = index
                    for key, value in action_list.items():
                        if key == "requirement":

                            if "disk_space" in value:
                                # self.set_message("Checking available space...")
                                available_disk = shutil.disk_usage(pathlib.Path.home().drive).free
                                available_disk_in_gb = available_disk / 1073741824
                                if available_disk_in_gb < int(value["disk_space"]):
                                    self.set_message("Recommended " + str(int(value["disk_space"])) + "GB minimum space to install, are you sure you want to continue?")
                            
                            # the isinstance method short circuits an impossible index attempt on a non-list 
                            if isinstance(value, list) and "must_exist" in value[0] or isinstance(value, list) and "must_exist_file_ending":
                                if "must_exist" in value[0]:
                                    if not os.path.exists(os.path.join(self.install_config["confirmed_install"], value[0]["must_exist"])) and not os.path.exists(os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"]), value[0]["must_exist"])):
                                    # if above condition (must_exist file not found), then show the correct error message
                                        self.set_message(value[0]["if_no"])
                                if "must_exist_file_ending" in value[0]:
                                    if not self.is_extension_in_directory(os.path.join(self.install_config["confirmed_install"]), value[0]["must_exist_file_ending"]) and not self.is_extension_in_directory(os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"])), value[0]["must_exist_file_ending"]):
                                        self.set_message(value[0]["if_no"])

                        elif key == "website":
                            website = value
                            # if there's no subdirectory, set to empty string so we don't get errors trying to read this key
                            if "sub_directory" not in website:
                                website["sub_directory"] = ""
                            is_installed = True
                            # if website["use_symlinks"] == True:
                            #     elevate()

                            # Check if a file is already installed 
                            print(value)
                            if "check" in value:
                                # print(os.path.abspath(__file__))
                                for file_or_dir in value["check"]:
                                    print(file_or_dir, os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], file_or_dir["after_install_file_or_dir"]))
                                    if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], file_or_dir["after_install_file_or_dir"])):
                                        is_installed = False

                            
                            # final case - if we don't need to install, consider it installed (all installs should have 'check' in yaml)
                            # if "check" in value.keys():
                            #     is_installed = True
                            if is_installed == True:
                                print(f"You're good to go on your previous installation for {value['file_name']}")
                                    
                            if is_installed == False:
                                # for every runthrough, check sizes on downloads (no reason to cache/store flag for something that takes 2 seconds)
                                self.install_config["install_steps"][index]["website"]["size_checked"] = False
                                # check if the file_name is already present for each website download
                                if not os.path.exists(os.path.join("modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], website["file_name"])):
                                    self.set_message("Downloading " + website["description"] + ": " + website["file_name"] + "\n\n"+ website["download_message"] +"\n\n" + "This may take a bit, so leave this window open and grab a cup of tea...")
                                    try:
                                        self.download_file(website["download_URL"], os.path.join("modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], website["file_name"]))  
                                    except Exception as exc:
                                        self.set_message('Encountered unknown error: '+ str(exc) + ' while trying to download ' + website["file_name"] + ". Press anything to exit.")
                                        sys.exit()
                                # Check the filesize to make sure the files are fully downloaded (large files, so partial downloads are a pain to troubleshoot)
                                if self.install_config["install_steps"][index]["website"]["size_checked"] == False:
                                    # self.set_message("Checking file size for downloaded "+ website["file_name"] +", press NEXT to continue...")
                                    result_bool = self.check_size(website["download_URL"], os.path.join(os.path.join("modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], website["file_name"])))
                                    if result_bool == False:
                                        os.remove(os.path.join(os.path.join("modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], website["file_name"]))) 
                                        self.set_message("Removing faulty download, please restart installer to resume.")
                                        sys.exit()
                                    else: 
                                        self.install_config["install_steps"][index]["website"]["size_checked"] = True
                                        # self.set_message("Filesize match. Press NEXT to continue...")
                                # Attempt unzip if the file exists
                                if ".zip" in website["file_name"]:
                                    try:
                                        # self.set_message("Press NEXT to unzip" + " " + website["file_name"] + "...")
                                        zipfile.ZipFile(os.path.join(os.path.join("modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], website["file_name"]))).extractall(os.path.join("modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"]))
                                    except RuntimeError:
                                        print("Not a zip file; " + website["file_name"])
                                # if we find the file itself but not the 'is_installed' checks, we must still install it
                                # if os.path.exists(website["file_name"]):
                                if "installation_hint" in website.keys():
                                    self.set_message("Please complete the " + website["file_name"]  + " executable install process. This window will automatically continue when the installer closes.\n\n" + website["installation_hint"])
                                # else:
                                #     self.set_message("Download completed!")
                                if "installer" in website.keys():
                                    for specific_installer in website["installer"]:
                                        # print(specific_installer)
                                        if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], specific_installer)):
                                            print("Couldn't find " + os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], specific_installer) + "...")
                                            sys.exit()
                                        print("Running:", os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], specific_installer))
                                        if "use_symlinks" not in website.keys():
                                            website["use_symlinks"] = False

                                        if website["use_symlinks"] == True:
                                            # using os.symlink() method
                                            already_exist_dir = self.install_config["confirmed_install"] # Replace with the path of your source directory
                                            symlinks_created_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"])  # Replace with the path of your target directory
                                            marker_file_name = "Mod_manager_marker.txt"

                                            try:
                                                for dirpath, dirnames, filenames in os.walk(already_exist_dir):
                                                    relative_path = os.path.relpath(dirpath, already_exist_dir)
                                                    for filename in filenames:
                                                        source_file = os.path.join(dirpath, filename)
                                                        target_dir_subfolder = os.path.join(symlinks_created_dir, relative_path)
                                                        os.makedirs(target_dir_subfolder, exist_ok=True)
                                                        target_link = os.path.join(target_dir_subfolder, filename)
                                                        if not os.path.exists(target_link):
                                                            os.symlink(source_file, target_link)

                                                        # Create a marker file in each directory when it's created
                                                        with open(os.path.join(target_dir_subfolder, marker_file_name), 'w') as marker_file:
                                                            marker_file.write("This is a marker file")
                                            except Exception as e:
                                                print(e)
                                            
                                            print("Symbolic link created successfully")
                                            self.vfs.run_process(os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], specific_installer), os.path.join(self.install_config["confirmed_install"], website["sub_directory"]))

                                            try:
                                                # Go through the symlink directory to remove empty directories and manage marker files
                                                for dirpath, dirnames, filenames in os.walk(symlinks_created_dir, topdown=False):
                                                    # Check if the directory contains the marker file and only symbolic links
                                                    if marker_file_name in filenames and all(os.path.islink(os.path.join(dirpath, f)) for f in filenames if f != marker_file_name):
                                                        # Remove all symbolic links
                                                        for filename in filenames:
                                                            file_path = os.path.join(dirpath, filename)
                                                            if os.path.islink(file_path):
                                                                os.unlink(file_path)
                                                        # If the directory is now empty (except for the marker file), remove the directory and the marker file
                                                        if len(os.listdir(dirpath)) == 1:
                                                            os.remove(os.path.join(dirpath, marker_file_name))  # remove the marker file
                                                            os.rmdir(dirpath)  # remove the directory
                                                    elif marker_file_name in filenames:
                                                        # If the directory contains other files besides symlinks and the marker file, just remove the marker file
                                                        os.remove(os.path.join(dirpath, marker_file_name))  # remove the marker file
                                            except Exception as e:
                                                print(e)
                                        else:
                                            self.vfs.run_process(os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"], website["sub_directory"], specific_installer))

                                # else:
                                    # check file exists locally
                                    # if not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"], website["file_name"])):
                                    #     print("Couldn't find the file " + os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"], website["file_name"]) + "...")
                                    #     sys.exit()
                                    # run file from game folder
                                    # file_to_run = os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"], website["installer"][0]))
                                    # file_working_directory = os.path.join(os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"])) # self.install_config["confirmed_install"]

                                    # if website["requires_admin"]:
                                    # print("Requires admin, running:", os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.bat"))
                                    # print(os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"], website["file_name"]))
                                    # self.vfs.run_process(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.bat") + " " + os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"], self.install_config["closeout"]["sub_directory"], self.install_config["closeout"]["run_file"]), os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"], self.install_config["closeout"]["sub_directory"]), blocking=False)

                                    # exit()
                                    # else:
                                    # self.vfs.run_process("notepad.exe")
                                    # self.vfs.run_process(file_to_run, file_working_directory)
                        
                        else: 
                            print("YAML file was unreadable, found neither 'requirement' or 'website'...")
                            sys.exit()

                print(os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"], self.install_config["closeout"]["run_file"]))
                # self.vfs.run_process(os.path.join(os.path.dirname(os.path.abspath(__file__)), "run.bat") + " " + os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"], self.install_config["closeout"]["sub_directory"], self.install_config["closeout"]["run_file"]), os.path.join(os.path.dirname(os.path.abspath(__file__)), self.install_config["default_config"]["virtual_game_folder"], self.install_config["closeout"]["sub_directory"]), blocking=False)
                # change directory to the game folder (not mod folder)
                # os.chdir(self.install_config["confirmed_install"])
                # run the game launcher (must still be in vfs to work)
                # print("Trying to run:", os.path.join(self.install_config["default_config"]["virtual_game_folder"], self.install_config["closeout"]["run_file"]), "at", os.path.join(self.install_config["confirmed_install"], self.install_config["closeout"]["sub_directory"]).replace("\\", "/"))
                self.window.close()
                self.vfs.run_process(os.path.join(os.path.dirname(os.path.abspath(__file__)), "modpacks", self.install_config["default_config"]["virtual_game_folder"], self.install_config["closeout"]["sub_directory"], self.install_config["closeout"]["run_file"]), blocking=True)

                # self.vfs.run_process("notepad.exe")
                # self.set_message(self.install_config["closeout"]["goodbye_message"])
                self.has_run = True

                self.vfs.close()
                sys.exit()

if "__main__":

    picker = ModPicker()
    yaml_location, must_elevate = picker.run()

    if must_elevate:
        elevate(show_console=False)
        # pass
        # elevate()
        # exit()

    downloader = Downloader(yaml_location)
    downloader.run()
