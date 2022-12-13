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

class Downloader:
    def __init__(self, install_config):
        # Tracks steps
        self.index = 1
        # metadata
        self.has_run = False
        self.find_steam_installation = False
        # Config object
        self.install_config = install_config
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
            [sg.Image("meta-installer-config/banner.png", size=(150,150), expand_x=True)],
            [sg.Text(self.step, size=(None, None), font='ANY 42', key="STEP", pad=(20, 30))], 
            [sg.HorizontalSeparator()],
            [sg.Text(self.main_message, size=(60, None), font = "ANY 20", key="MAIN_MESSAGE", pad=(40, 40))], 
            [
                sg.Button("NEXT", key="OK", font='ANY 20', size=(10, None))
            ]
        ]
        # Create the window
        self.window = sg.Window("Easy Installer", default_element_size=(20, 1), layout=layout, element_justification='c', icon="meta-installer-config/exe-icon.ico", enable_close_attempted_event=True)
        # Load install.yaml config
        with open('meta-installer-config/install.yaml', 'r') as file:
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
        if int(content_length) != os.stat(local_file).st_size:
            self.set_message("File size unmatch for " + local_file + " from " + url + "\n" + content_length + " online vs. " + str(os.stat(local_file).st_size) + " locally.")
            return False
        return True

    def download_file(self, url, local_filename):
        # first use moddb workaround for relevant files
        url = self.find_moddb_download(url)
        headers = {
            "User-Agent": self.install_config["default_config"]["user_agent"],
        }
        content_length = requests.get(url, headers=headers, stream=True).headers['Content-length']
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status()
            with open(local_filename, 'wb') as f:
                for chunk in r.iter_content(chunk_size=8192): 
                    f.write(chunk)
                    i = os.path.getsize(local_filename)
                    ret_flag = sg.OneLineProgressMeter(local_filename + " Download", i+1, int(content_length),  'Download initiated.', 'Transferring data through hyper-relays.', grab_anywhere=True)
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
            if not self.find_steam_installation:
                if self.install_config["default_config"]["steam_setup"] == True:
                    try:
                        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "SOFTWARE\WOW6432Node\Valve\Steam")
                    except:
                        hkey = None
                        print(sys.exc_info())
                        sys.exit()
                else: 
                    self.find_steam_installation = True
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
                            self.set_message("Found the Steam installation directory at:\n\n" + self.install_config["confirmed_install"])
                    except e:
                        print(e)
                        sys.exit()
                if len(self.install_config["installation_paths"]) == 0:
                    print("Could not find Steam installation directory. You could always disable Steam detection in settings if you're not using Steam.")
                    self.set_message("Could not find Steam installation directory. You could always disable Steam detection in settings if you're not using Steam.")
                    sys.exit()
                else:
                    os.chdir(self.install_config["confirmed_install"])
                self.find_steam_installation == True

            # go through each install.yaml install_steps action
            if not self.has_run:
                for index, action_list in enumerate(self.install_config["install_steps"]):
                    # update index (how progress is tracked)
                    self.index = index
                    for key, value in action_list.items():
                        if key == "requirement":

                            if "disk_space" in value:
                                self.set_message("Checking available space...")
                                available_disk = shutil.disk_usage(pathlib.Path.home().drive).free
                                available_disk_in_gb = available_disk / 1073741824
                                if available_disk_in_gb < int(value["disk_space"]):
                                    self.set_message("Recommended " + str(int(value["disk_space"])) + "GB minimum space to install, are you sure you want to continue?")
                                else:
                                    self.set_message("Has ample space of " + str(int(value["disk_space"])) + "GB for installation! Press Next to continue.")
                            
                            # the isinstance method short circuits an impossible index attempt on a non-list 
                            if isinstance(value, list) and "must_exist" in value[0] or isinstance(value, list) and "must_exist_file_ending":
                                if "must_exist" in value[0] and not os.path.exists(value[0]["must_exist"]):
                                    # if above condition (must_exist file not found), then show the correct error message
                                    self.set_message(value[0]["if_no"])
                                if "must_exist_file_ending" in value[0]:
                                    #perform the same check and error if the file must have a specific ending
                                    result = [x for x in os.listdir() if len(x) >= len(value[0]["must_exist_file_ending"]) and x[-len(value[0]["must_exist_file_ending"]):].lower() == value[0]["must_exist_file_ending"].lower()]
                                    result = bool(result)
                                    if not bool(result):
                                        self.set_message(value[0]["if_no"])

                        elif key == "website":
                            is_installed = False
                            # check if there's a 'check' on the website, since we can skip everything else if there is and we meet the criteria
                            if "check" in value.keys():
                                # is this too much of a hack? Anyway, if after_install_file_or_dir returns a hit (should only ever be one), act on it
                                try:
                                    if len(value["check"][next((i) for i,d in enumerate(value["check"]) if "after_install_file_or_dir" in d)]) > 0:
                                        if os.path.exists(value["check"][next((i) for i,d in enumerate(value["check"]) if "after_install_file_or_dir" in d)]["after_install_file_or_dir"]):
                                            is_installed = True
                                        else: 
                                            is_installed = False
                                except (KeyError, StopIteration) as e:
                                    pass
                                try:
                                    #same for the next check (only valid if first check happens) for file_content
                                    if len(value["check"][next((i) for i,d in enumerate(value["check"]) if "after_install_file_or_dir" in d)]) > 0 and len(value["check"][next((i) for i,d in enumerate(value["check"]) if "file_content" in d)]) > 0:
                                        filename = value["check"][next((i) for i,d in enumerate(value["check"]) if "after_install_file_or_dir" in d)]["after_install_file_or_dir"]
                                        with open(filename, "r") as file:
                                            content = file.read()
                                            if value["check"][next((i) for i,d in enumerate(value["check"]) if "file_content" in d)]["file_content"] in content: 
                                                is_installed = True
                                            else:
                                                is_installed = False
                                except (KeyError, StopIteration) as e:
                                    pass
                                if is_installed == True:
                                    self.set_message("You're good to go on your previous installation for " + value["file_name"])
                            
                            # final case - if we don't need to install, consider it installed (all installs should have 'check' in yaml)
                            if os.path.exists(value["file_name"]) and not "check" in value.keys():
                                is_installed = True
                                    
                            if is_installed == False:
                                # for every runthrough, check sizes on downloads (no reason to cache/store flag for something that takes 2 seconds)
                                self.install_config["install_steps"][index]["website"]["size_checked"] = False
                                website = value
                                # check if the file_name is already present for each website download
                                if not os.path.exists(website["file_name"]):
                                    self.set_message("Downloading " + website["description"] + ": " + website["file_name"] + "\n\n"+ website["download_message"] +"\n\n" + "This may take a bit, so leave this window open and grab a cup of tea...")
                                    try:
                                        self.download_file(website["download_URL"], website["file_name"])
                                    except Exception as exc:
                                        self.set_message('Encountered unknown error: '+ str(exc) + ' while trying to download ' + website["file_name"] + ". Press anything to exit.")
                                        sys.exit()
                                # Check the filesize to make sure the files are fully downloaded (large files, so partial downloads are a pain to troubleshoot)
                                if self.install_config["install_steps"][index]["website"]["size_checked"] == False:
                                    self.set_message("Checking file size for downloaded "+ website["file_name"] +", press NEXT to continue...")
                                    result_bool = self.check_size(website["download_URL"], website["file_name"])
                                    if result_bool == False:
                                        os.remove(website["file_name"]) 
                                        self.set_message("Removing faulty download, please restart installer to resume.")
                                        sys.exit()
                                    else: 
                                        self.install_config["install_steps"][index]["website"]["size_checked"] = True
                                        self.set_message("Filesize match. Press NEXT to continue...")
                                # Attempt unzip if the file exists
                                if ".zip" in website["file_name"]:
                                    try:
                                        self.set_message("Press NEXT to unzip" + " " + website["file_name"] + "...")
                                        zipfile.ZipFile(website["file_name"]).extractall()
                                    except RuntimeError:
                                        print("Not a zip file; " + website["file_name"])
                                # if we find the file itself but not the 'is_installed' checks, we must still install it
                                if os.path.exists(website["file_name"]):
                                    if "installation_hint" in website.keys():
                                        self.set_message("Please complete the " + website["file_name"]  + " executable install process. This window will automatically continue when the installer closes.\n\n" + website["installation_hint"])
                                    else:
                                        self.set_message("Please complete the " + website["file_name"]  + " executable install process. This window will automatically continue when the installer closes.")
                                    if "installer" in website.keys():
                                        for specific_installer in website["installer"]:
                                            if not os.path.exists(specific_installer):
                                                print("Couldn't find " + specific_installer + "...")
                                                sys.exit()
                                            sg.execute_command_subprocess(specific_installer, wait=True)
                                    else:
                                        if not os.path.exists(website["file_name"]):
                                            print("Couldn't find " + website["file_name"] + "...")
                                            sys.exit()
                                        sg.execute_command_subprocess(website["file_name"], wait=True)
                        
                        else: 
                            print("YAML file was unreadable, found neither 'requirement' or 'website'...")
                            sys.exit()
                

                os.startfile(self.install_config["closeout"]["run_file"])
                self.set_message(self.install_config["closeout"]["goodbye_message"])
                self.has_run = True

        self.window.close()

if "__main__":
    downloader = Downloader("install.yaml")
    downloader.run()
