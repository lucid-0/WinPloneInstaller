import subprocess as sp
import os
import platform
import time
from winreg import *
from tkinter import *
from tkinter import messagebox
from tkinter.ttk import *

class WindowsPloneInstaller:

    def __init__(self):
        try:
            self.base_path = sys._MEIPASS  # PyInstaller creates a temp folder and stores path in _MEIPASS environment variable
        except Exception:
            self.base_path = os.path.abspath(".")

        self.plone_key = r'SOFTWARE\PloneInstaller' #our Windows registry key under HKEY_CURRENT_USER
        self.run_once_key = r'Software\Microsoft\Windows\CurrentVersion\RunOnce'

        self.installer_path = os.path.realpath(__file__).split(".")[0]+".exe"
        self.log_file = os.path.dirname(self.installer_path) + "\install.log"

        self.required_build = 15063

        try: #Grab installation state from registry if it exists
            k = OpenKey(HKEY_CURRENT_USER, self.plone_key, 0, KEY_ALL_ACCESS)
            self.install_status = QueryValueEx(k, "install_status")[0]

        except: #Otherwise create it with ititial "begin" value
            k = CreateKey(HKEY_CURRENT_USER, self.plone_key)
            self.install_status = "begin"
            SetValueEx(k, "install_status", 1, REG_SZ, self.install_status)

        SetValueEx(k, "base_path", 1, REG_SZ, self.base_path) #This ensures powershell and bash can find this path.
        SetValueEx(k, "installer_path", 1, REG_SZ, os.path.dirname(self.installer_path))
        CloseKey(k)

        self.last_status = self.install_status
        self.init_GUI()

    def init_GUI(self):
        self.gui = Tk()
        self.gui.title("Windows Plone Installer")
        window_width = 500
        window_height = 325
        self.fr1 = Frame(self.gui, width=window_width, height=window_height)
        self.fr1.pack(side="top")

        #GUI Row 0
        self.log_text = Text(self.fr1, borderwidth=3, relief="sunken",spacing1=1, height=8, width=50, bg="black", fg="white")
        self.log_text.config(font=("consolas", 12), undo=True, wrap='word')
        self.log_text.grid(row=0, column=0, sticky="nsew", padx=2, pady=2) 

        scrollb = Scrollbar(self.fr1, command=self.log_text.yview)
        scrollb.grid(row=0, column=1, sticky='nsew')
        self.log_text['yscrollcommand'] = scrollb.set

        #GUI Row 1
        self.start_plone = IntVar(value=1)
        Checkbutton(self.fr1, text="Start Plone after installation", variable=self.start_plone).grid(row=1,sticky="EW")

        #GUI Row 2
        self.default_password = IntVar(value=1)
        Checkbutton(self.fr1, text="Use username:admin password:admin for Plone (otherwise be prompted)", variable=self.default_password).grid(row=2,sticky="EW")

         #GUI Row 3
        self.default_directory = IntVar(value=1)
        Checkbutton(self.fr1, text="Install to default directory (/etc/Plone, otherwise be prompted)", variable=self.default_directory).grid(row=3, sticky="EW")

         #GUI Row 4
        self.auto_restart = IntVar(value=1)
        self.auto_restart_checkbutton = Checkbutton(self.fr1, text="Prompt for reboot (otherwise automatic)", variable=self.auto_restart)
        self.auto_restart_checkbutton.grid(row=4,stick="EW")

        #GUI Row 5
        self.okaybutton = Button(self.fr1, text="Okay")
        self.okaybutton.grid(row=5, sticky="WE")
        self.okaybutton.bind("<Button>", self.okay_handler)

        #GUI Row 6
        cancelbutton = Button(self.fr1, text="Cancel")
        cancelbutton.grid(row=6, sticky="WE")
        cancelbutton.bind("<Button>", self.killapp)
        self.fin = ''

        #GUI Settings
        ws = self.gui.winfo_screenwidth()
        hs = self.gui.winfo_screenheight()
        x = (ws/2) - (window_width/2)
        y = (hs/2) - (window_height/2)
        self.gui.geometry('%dx%d+%d+%d' % (window_width, window_height, x, y))

        self.log("Welcome to Plone Installer for Windows.")

        if self.install_status == "begin":
                self.log("Press 'Okay' to launch PowerShell, gather information about your system and prepare to install Plone.")
            
        elif self.install_status == "enabling_wsl":
            self.log("Picking up where we left off. Installing Linux Subsystem...")
            self.get_reg_vars() #grab user's installation config values from registry
            self.init_install()

        else:
            self.catch()

        self.gui.mainloop()
        
    def okay_handler(self, event): #handle the event and allow init_install to be called without an event
        self.init_install()

    def init_install(self):

        self.okaybutton.configure(state="disabled")

        self.update_scripts()
        self.log('Checking for Linux Subsystem (WSL)')
        self.set_reg_vars() #put user's installation config variables in registry in case we have to restart.
        self.run_PS("enable_wsl.ps1") #Make sure WSL is enabled and check if it is already installed
        #messagebox.showinfo(title='after call to run_ps')
        self.wait_for_status_change(45)

        if self.install_status == "install_with_buildout":
            self.log("Simple buildout installation will be used. Windows 10 with Creator's Update is required for WSL installation (recommended)")
            self.buildout_install()
        elif self.install_status == "enabling_wsl":
            SetValue(HKEY_CURRENT_USER, self.run_once_key, REG_SZ, self.installer_path) #Set Win Registry to load our installer after the next restart
            self.log('Enabling Linux Subsystem, Please allow PowerShell to restart for you.')
        elif self.install_status == "wsl_enabled":
            self.log('Linux Subsystem enabled.')
            self.log('Installing the Linux Subsystem.')
            self.run_PS("install_wsl.ps1")
            self.wait_for_status_change(2000)

            if self.install_status == "wsl_installed":
                self.log('Installed the linux subsystem, now installing Plone.')
                self.wsl_install()
            
            else:
                catch()

        elif self.install_status == "wsl_installed":
            self.log('Linux Subsystem previously installed, installing Plone')
            self.wsl_install()

        else:
            catch()

    def wsl_install(self):
        self.run_PS("install_plone_wsl.ps1") #Install Plone on the new instance of WSL
        self.wait_for_status_change(5000) # Not sure how long this takes

        if self.install_status == "complete":
            log("Plone installed successfully on Linux subsystem!")
            self.clean_up()
        else:
            catch()

    def buildout_install(self):
        self.log('Installing Chocolatey package manager')
        self.run_PS("install_choco.ps1") #Chocolatey will allow us to grab dependencies.
        self.wait_for_status_change(90)

        if self.install_status == "choco_installed":
            self.log('Chocolatey Installed')
            self.log('Installing Plone Dependencies using Chocolatey')
            self.run_PS("install_plone_buildout.ps1")  #Run the regular Plone buildout script for users who are not using Ubuntu/Bash

            self.wait_for_status_change(300)

            if self.install_status == "dependencies_installed":
                self.log("Dependencies installed.")
                self.log("Preparing virtualenv and gathering Plone buildout from GitHub.")
                self.wait_for_status_change(500)

                if self.install_status == "starting_buildout":
                    self.log("Running buildout, this may take a while...")

                    self.wait_for_status_change(5000) #Not sure how long this takes

                    if self.install_status == "complete":
                        log("Plone installed successfully!")
                        self.clean_up()
                    else:
                        self.catch()
                else:
                    self.catch()
            else:
                self.catch()
        else:
            self.catch()

    def update_scripts(self):

        with open(self.base_path + "\\PS\\enable_wsl.ps1", "a") as enable_script:
            if self.auto_restart.get() == False:
                enable_script.write('\nWrite-Host -NoNewLine "WinPloneInstaller needs to restart! It will continue when you return, press any key when ready..."')
                enable_script.write('\n$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")')
            
            enable_script.write("\nRestart-Computer } }") #fix these hack-it brackets

            enable_script.close()

        install_call = "sudo ./install.sh"

        if self.default_password.get():
            install_call += " --password=admin"

        if self.default_directory.get():
            install_call += " --target=/etc/Plone"

        install_call += " standalone"

        with open(self.base_path + "\\bash\\plone.sh", "a") as bash_script:
            bash_script.write(";"+install_call) #I've done this using ; for now because Windows new line characters are written instead of Unix ones.

            if self.start_plone.get():
                bash_script.write(";sudo /etc/Plone/zinstance/bin/plonectl start") #this line will start plone in WSL

            #bash_script.write(";rm -rf ") #this will delete the universal installer archive and directory
            bash_script.close()
            
        if self.start_plone.get():
            with open(self.base_path + "\\PS\\install_plone_buildout.ps1", "a") as buildout_script:
                    buildout_script.write('\nbin\instance start')

                    buildout_script.close()
                        
    def set_reg_vars(self):
        k = OpenKey(HKEY_CURRENT_USER, self.plone_key, 0, KEY_ALL_ACCESS)
        SetValueEx(k, "start_plone", 1, REG_SZ, str(self.start_plone.get()))
        SetValueEx(k, "default_directory", 1, REG_SZ, str(self.default_directory.get()))
        SetValueEx(k, "default_password", 1, REG_SZ, str(self.default_password.get()))
        SetValueEx(k, "auto_restart", 1, REG_SZ, str(self.auto_restart.get()))

    def get_reg_vars(self):
        k = OpenKey(HKEY_CURRENT_USER, self.plone_key, 0, KEY_ALL_ACCESS)
        self.start_plone.set(int(QueryValueEx(k, "start_plone")))
        self.default_directory.set(int(QueryValueEx(k, "default_directory")))
        self.default_password.set(int(QueryValueEx(k, "default_password")))
        self.auto_restart.set(int(QueryValueEx(k, "auto_restart")))

    def run_PS(self, script_name):
        script_path = self.base_path+"\\PS\\"+script_name
        self.log("Calling " + script_name + " in Microsoft PowerShell, please accept any prompts.")
        ps_process = sp.Popen(["C:\\WINDOWS\\system32\\WindowsPowerShell\\v1.0\\powershell.exe", ". " + script_path], shell=True, stdin=None, stdout=None, stderr=None, close_fds=True)
        #sp.run(["C:\\WINDOWS\\system32\\WindowsPowerShell\\v1.0\\powershell.exe", ". " + script_path])

    def wait_for_status_change(self, timeout):
        k = OpenKey(HKEY_CURRENT_USER, self.plone_key, 0, KEY_ALL_ACCESS)
        count = 0
        while self.install_status == self.last_status:
            time.sleep(2) #to prevent this from overkill
            self.install_status = QueryValueEx(k, "install_status")[0]
            count += 1
            if count == timeout:
                self.install_status = "timed_out"
                break
        self.last_status = self.install_status
        CloseKey(k)
        return

    def catch(self):
        if self.install_status == "timed_out":
                log("Installer process timed out!")

    def log(self, message):
        with open(self.log_file, "a") as log:
            log.write(message+"\n")
        self.log_text.config(state="normal")
        self.log_text.insert(END, "> " + message + '\n')
        self.log_text.config(state="disabled")
        self.log_text.see(END)
        self.gui.update()

    def clean_up(self):
        self.log('Cleaning up.')
        k = OpenKey(HKEY_CURRENT_USER, self.plone_key, 0, KEY_ALL_ACCESS)
        DeleteKey(k, "install_status")
        DeleteKey(k, "base_path")
        DeleteKey(k, "installer_path")
        DeleteKey(k, "win_version")
        CloseKey(k)
        DeleteKey(HKEY_CURRENT_USER, self.plone_key)

    def killapp(self, event):
        sys.exit(0)

if __name__ == "__main__":
    try:
        app = WindowsPloneInstaller()
    except KeyboardInterrupt:
        raise SystemExit("Aborted by user request.")