import subprocess as sp
import os
# import win32api
# import platform
import time
from winreg import *
from tkinter import *
from tkinter.ttk import *

class WindowsPloneInstaller:

    def __init__(self):
        try:
            self.base_path = sys._MEIPASS  # PyInstaller creates a temp folder and stores path in _MEIPASS environment variable
        except Exception:
            self.base_path = os.path.abspath(".")

        self.installer_path = os.path.realpath(__file__).split(".")[0]+".exe"

        self.plone_key = r'SOFTWARE\PloneInstaller' #our Windows registry key under HKEY_CURRENT_USER
        self.run_once_key = r'Software\Microsoft\Windows\CurrentVersion\RunOnce'

        self.required_build = 15063

        try: #Grab installation state from registry if it exists
            k = OpenKey(HKEY_CURRENT_USER, self.plone_key)
            self.install_status = QueryValueEx(k, "install_status")[0]

        except: #Otherwise create it with ititial "begin" value
            k = CreateKey(HKEY_CURRENT_USER, self.plone_key)
            self.install_status = "begin"
            SetValueEx(k, "install_status", 0, REG_SZ, self.install_status)

        SetValueEx(k, "base_path", 0,REG_SZ, self.base_path) #This ensures powershell and bash can find this path.

        self.last_status = self.install_status
        self.init_GUI()

    def killapp(self, event):
        sys.exit(0)

    def init_GUI(self):
        self.root = Tk()
        self.root.title("Windows Plone Installer")
        self.fr1 = Frame(self.root, width=300, height=100)
        self.fr1.pack(side="top")

        self.fr2 = Frame(self.root, width=300, height=300,
                    borderwidth=2, relief="ridge")
        self.fr2.pack(ipadx=10, ipady=10)
        self.fr4 = Frame(self.root, width=300, height=100)
        self.fr4.pack(side="bottom", pady=10)

        self.status_text = StringVar()
        self.status_text.set('Welcome to Plone Installer for Windows.')
        statusLabel = Label(self.fr2, textvariable=self.status_text)
        statusLabel.grid(sticky="NW")

        if self.install_status == "wsl_enabled":
            self.status_text.set('Picking up where we left off. Installing Linux Subsystem...')
            self.run_PS("./PS/installWSL.ps1") #Install Ubuntu on Windows
            self.wait_for_status_change(5000) # Not sure how long this takes

            if self.install_status == "wsl_installed":
                self.run_PS("./PS/installPlone.ps1") #Install Plone on the new instance of WSL
                self.wait_for_status_change(5000) # Not sure how long this takes

            elif self.install_status == "timed_out":
                print("Installer process timed out!")

        elif self.install_status == "begin":
            self.run_PS("./PS/getWinInfo.ps1")
            self.wait_for_status_change(10)

            if self.install_status == "got_win_info":
                k = OpenKey(HKEY_CURRENT_USER, self.plone_key)
                
                env_build = int(str(QueryValueEx(k, "win_version")).split('.')[2].split("'")[0]) #this feels 'rigged.' Moved it to PowerShell because it's much more reliable, however.

                if env_build >= self.required_build:
                    self.install_type = IntVar(value=1)
                    checkbox = Checkbutton(self.fr2, text="Install using Ubuntu for Windows (recommended)", variable=self.install_type)
                    checkbox.grid(sticky="NW")
                else:
                    self.install_type = IntVar(value=0)
                    self.status_text.set("You do not have a new enough version of Windows to install with Ubuntu for Windows.\n Please install Creator's Update or newer to use Ubuntu.\nOr press OK to install using standard buildout.")

        #else:
            # This shouldn't really happen.
            # Is another instance of the installer already running? Should we start installion over?

        okaybutton = Button(self.fr4, text="Okay   ")
        okaybutton.bind("<Button>", self.init_install)
        okaybutton.pack(side="left")

        cancelbutton = Button(self.fr4, text="Cancel")
        cancelbutton.bind("<Button>", self.killapp)
        cancelbutton.pack(side="right")
        self.fin = ''

        ws = self.root.winfo_screenwidth()
        hs = self.root.winfo_screenheight()
        x = (ws/2) - (400/2)
        y = (hs/2) - (250/2)
        self.root.geometry('%dx%d+%d+%d' % (400, 250, x, y))

        self.root.mainloop()
        
    def init_install(self, event):

        if self.install_type.get(): #if this is true, this machine has proper version for WSL route
            self.status_text.set('Checking for Linux Subsystem')
            SetValue(HKEY_CURRENT_USER, self.run_once_key, REG_SZ, self.installer_path) #Set Win Registry to load our installer after the next restart
            self.run_PS("./PS/enableWSL.ps1") #Make sure WSL is enabled and check if it is already installed
            self.wait_for_status_change(15)

            if self.install_status == "wsl_enabled":
                self.status_text.set('Linux Subsystem enabled. Must restart to install it...')

            elif self.install_status == "wsl_installed":
                self.status_text.set('Linux Subsystem already installed, installing Plone')
                self.run_PS("./PS/installPlone.ps1") #User already had WSL installed, Install Plone on existing subsystem.

            elif self.install_status == "timed_out":
                print("Installer process timed out!")

        else: #either this machine isn't high enough version,or user has selected standard buildout route manually.
            self.status_text.set('Installing Chocolatey package manager')
            self.run_PS("./PS/installChoco.ps1") #Chocolatey will allow us to grab dependencies.
            self.wait_for_status_change(90)

            if self.install_status == "choco_installed":
                self.status_text.set('Chocolatey Installed...')
                self.run_PS("./PS/installPloneBuildout.ps1")  #Run the regular Plone buildout script for users who are not using Ubuntu/Bash

                self.wait_for_status_change(5000) #Not sure how long this takes

            elif self.install_status == "timed_out":
                print("Installer process timed out!")

    def run_PS(self, script_name):
        script_path = self.base_path + script_name
        #sp.call(["C:\\WINDOWS\\system32\\WindowsPowerShell\\v1.0\\powershell.exe", ". " + script_path, "-ExecutionPolicy", "Unrestricted", "-windowstyle", "hidden;"]) #these -options aren't actually working.
        sp.run(["C:\\WINDOWS\\system32\\WindowsPowerShell\\v1.0\\powershell.exe", ". " + script_path, "-ExecutionPolicy", "Unrestricted", "-windowstyle", "hidden;"])

    def wait_for_status_change(self, timeout): #add a timeout here in case, for example, powershell crashes before updating status
        k = OpenKey(HKEY_CURRENT_USER, self.plone_key)
        count = 0
        while self.install_status == self.last_status:
            time.sleep(2) #to prevent this from overkill
            self.install_status = QueryValueEx(k, "install_status")[0]
            count += 1
            if count == timeout:
                self.install_status = "timed_out"
                break
        self.last_status = self.install_status
        return

if __name__ == "__main__":
    try:
        app = WindowsPloneInstaller()
    except KeyboardInterrupt:
        raise SystemExit("Aborted by user request.")