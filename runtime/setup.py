import sys
import shutil
import os.path
import configparser
import logging
import time
import urllib.request
import traceback
import platform
import zipfile
sys.path.append(os.path.dirname(os.path.realpath(__file__)))  # Workaround for python 3.6's obtuse import system.
import minecraftversions

class InstallMC:
    _default_config = 'conf/mcp.cfg'
    _version_config = 'conf/version.cfg'

    def __init__(self, conffile=None):
        self.conffile = conffile
        self.readconf()
        if platform.system() == "Windows":
            self.platform = "windows"
        elif platform.system() == "Darwin":
            self.platform = "macosx"
        else:
            self.platform = "linux"
        self.confdir = self.config.get("DEFAULT", "DirConf")
        self.jardir = self.config.get("DEFAULT", "DirJars")
        self.tempdir = self.config.get("DEFAULT", "DirTemp")
        self.logdir = self.config.get("DEFAULT", "DirLogs")
        self.mcplogfile = self.config.get('MCP', 'LogFile')
        self.mcperrlogfile = self.config.get('MCP', 'LogFileErr')
        self.startlogger()

    def startlogger(self):
        """
        Basically sets up a logger and different logger handlers for different levels and such.
        Code copied from commands.py:92
        :return:
        """
        if not os.path.exists(self.logdir):
            os.makedirs(self.logdir)
        self.logger = logging.getLogger('MCPLog')
        self.logger.setLevel(logging.DEBUG)
        # create file handler which logs even debug messages
        fh = logging.FileHandler(filename=self.mcplogfile, mode='w')
        fh.setLevel(logging.DEBUG)
        # create console handler with a higher log level
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        # File output of everything Warning or above
        eh = logging.FileHandler(filename=self.mcperrlogfile, mode='w')
        eh.setLevel(logging.WARNING)
        # create formatter and add it to the handlers
        formatterconsole = logging.Formatter('%(message)s')
        ch.setFormatter(formatterconsole)
        formatterfile = logging.Formatter('%(asctime)s - %(module)11s.%(funcName)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M')
        fh.setFormatter(formatterfile)
        eh.setFormatter(formatterfile)
        # add the handlers to logger
        self.logger.addHandler(ch)
        self.logger.addHandler(fh)
        self.logger.addHandler(eh)

    def start(self, scriptsonly=False):
        """
        Main entry function.
        :return:
        """
        self.logger.info("\n> Python: " + sys.version)

        self.logger.info("> Welcome to the RetroMCP setup script!")
        self.logger.info("> This script will automatically set up your MCP workspace.")

        if os.path.exists("src"):
            self.logger.info("\n! /src exists! Aborting.")
            self.logger.info("! Run cleanup in order to run setup again.")
            sys.exit()

        self.logger.info("\n> Setting up your workspace...")

        self.logger.info("\n> Making sure temp exists...")
        if not os.path.exists(self.tempdir):
            os.makedirs(self.tempdir)
        self.logger.info("> Making sure jars/bin/natives exists.")
        if not os.path.exists(os.path.join(self.jardir, "bin", "natives")):
            os.makedirs(os.path.join(self.jardir, "bin", "natives"))

        if scriptsonly:
            self.logger.info("\n> Copying scripts...")
            for file in os.listdir(os.path.join("runtime", self.platform + "_scripts")):
                shutil.copy2(os.path.join("runtime", self.platform + "_scripts", file), ".")
        else:
            natives = {
                "windows": {
                    "lwjgl": "https://repo1.maven.org/maven2/org/lwjgl/lwjgl/lwjgl-platform/2.8.4/lwjgl-platform-2.8.4-natives-windows.jar",
                    "jinput": "https://repo1.maven.org/maven2/net/java/jinput/jinput-platform/2.0.5/jinput-platform-2.0.5-natives-windows.jar"
                },
                "macosx": {
                    # macOS requires a newer LWJGL version
                    "lwjgl": "https://repo1.maven.org/maven2/org/lwjgl/lwjgl/lwjgl-platform/2.9.0/lwjgl-platform-2.9.0-natives-osx.jar",
                    "jinput": "https://repo1.maven.org/maven2/net/java/jinput/jinput-platform/2.0.5/jinput-platform-2.0.5-natives-osx.jar"
                },
                "linux": {
                    "lwjgl": "https://repo1.maven.org/maven2/org/lwjgl/lwjgl/lwjgl-platform/2.8.4/lwjgl-platform-2.8.4-natives-linux.jar",
                    "jinput": "https://repo1.maven.org/maven2/net/java/jinput/jinput-platform/2.0.5/jinput-platform-2.0.5-natives-linux.jar"
                }
            }
            lwjgl_version = "2.9.0" if self.platform == "macosx" else "2.8.4"
            self.logger.info("\n> Downloading LWJGL...")
            libtime = time.time()
            self.download("https://repo1.maven.org/maven2/org/lwjgl/lwjgl/lwjgl/" + lwjgl_version + "/lwjgl-" + lwjgl_version + ".jar", os.path.join(self.jardir, "bin", "lwjgl.jar"))
            self.download("https://repo1.maven.org/maven2/org/lwjgl/lwjgl/lwjgl_util/" + lwjgl_version + "/lwjgl_util-" + lwjgl_version + ".jar", os.path.join(self.jardir, "bin", "lwjgl_util.jar"))
            
            self.logger.info("> Downloading LWJGL natives for your platform...")
            self.download(natives[self.platform]["lwjgl"], os.path.join(self.jardir, "bin", "lwjgl_natives.zip"))

            self.logger.info("\n> Downloading JInput...")
            self.download("https://repo1.maven.org/maven2/net/java/jinput/jinput/2.0.5/jinput-2.0.5.jar", os.path.join(self.jardir, "bin", "jinput.jar"))
            self.logger.info("> Downloading JInput natives for your platform...")
            self.download(natives[self.platform]["jinput"], os.path.join(self.jardir, "bin", "jinput_natives.zip"))

            self.logger.info('> Done in %.2f seconds' % (time.time() - libtime))

            self.logger.info("\n> Extracting natives...")
            exttime = time.time()
            nativezip = zipfile.ZipFile(os.path.join(self.jardir, "bin", "lwjgl_natives.zip"))
            nativezip.extractall(os.path.join(self.jardir, "bin", "natives"))
            nativezip.close()
            if os.path.isfile(os.path.join(self.jardir, "bin", "lwjgl_natives.zip")):
                os.unlink(os.path.join(self.jardir, "bin", "lwjgl_natives.zip"))
            nativezip = zipfile.ZipFile(os.path.join(self.jardir, "bin", "jinput_natives.zip"))
            nativezip.extractall(os.path.join(self.jardir, "bin", "natives"))
            nativezip.close()
            if os.path.isfile(os.path.join(self.jardir, "bin", "jinput_natives.zip")):
                os.unlink(os.path.join(self.jardir, "bin", "jinput_natives.zip"))
            self.logger.info('> Done in %.2f seconds' % (time.time() - exttime))

            self.logger.info("\n> Copying scripts...")
            scripts_dir = 'unix_scripts' if self.platform != 'windows' else 'windows_scripts'

            for file in os.listdir(os.path.join("runtime", scripts_dir)):
                shutil.copy2(os.path.join("runtime", scripts_dir, file), ".")

            self.logger.info("\n> Setting up minecraft...")
            self.setupmc()


    def setupmc(self):
        self.logger.info("> If you wish to supply your own configuration, type \"custom\".")

        versions = []
        for version in os.listdir(self.confdir):
            if os.path.isdir(os.path.join(self.confdir, version)) and version != "patches" and version != "custom" and not os.path.exists(os.path.join(self.confdir, version, "DISABLED")):
                versions.append(version)
                versions.sort()
        inp = ""
        confname = inp
        foundmatch = False
        while not foundmatch:
            self.logger.info("> Current versions are:")
            for v in versions:
                for x in v.split(","):
                    self.logger.info(' - ' + x)
            self.logger.info("> What version would you like to install?")

            inp = str(input(": "))

            if inp == "custom":
                foundmatch = True
                confname = inp
            else:
                for y in versions:
                    for x in y.split(","):
                        if x == inp:
                            foundmatch = True
                            confname = y

        self.logger.info("> Copying config.")
        copytime = time.time()
        self.copydir(os.path.join(self.confdir, confname), self.confdir)
        with open(self._version_config, "a") as file:
            file.write('ClientVersion = ' + inp + '\n')
            if inp in minecraftversions.versions["client"]:
                if "server" in minecraftversions.versions["client"][inp]:
                    file.write('ServerVersion = ' + minecraftversions.versions["client"][inp]["server"] + '\n')
                elif inp in minecraftversions.versions["server"]:
                    file.write('ServerVersion = ' + inp + '\n')
        self.logger.info('> Done in %.2f seconds' % (time.time() - copytime))

        if inp != "custom":
            self.logger.info("> Downloading Minecraft client...")
            clientdltime = time.time()
            self.download(minecraftversions.versions["client"][inp]["url"],
                          os.path.join(self.jardir, "bin", "minecraft.jar"))
            self.logger.info('> Done in %.2f seconds' % (time.time() - clientdltime))
            ver = inp
            serverdltime = time.time()
            if ver in minecraftversions.versions["server"] or "server" in minecraftversions.versions["client"][ver]:
                self.logger.info("> Downloading Minecraft server...")
                ver2 = ver
                if "server" in minecraftversions.versions["client"][ver]:
                    ver2 = minecraftversions.versions["client"][ver]["server"]
                dlname = "minecraft_server.jar"
                extract = False
                if minecraftversions.versions["server"][ver2]["url"].endswith(".zip"):
                    dlname = "minecraft_server.zip"
                    extract = True
                self.download(minecraftversions.versions["server"][ver2]["url"], os.path.join(self.jardir, dlname))
                if extract:
                    self.logger.info("> Extracting Minecraft server...")
                    serverzip = zipfile.ZipFile(os.path.join(self.jardir, dlname))
                    serverzip.extractall(self.jardir)
                    serverzip.close()
                    if os.path.isfile(os.path.join(self.jardir, "minecraft-server.jar")):
                        os.rename(os.path.join(self.jardir, "minecraft-server.jar"),os.path.join(self.jardir, "minecraft_server.jar"))
                    if os.path.isfile(os.path.join(self.jardir, dlname)):
                        os.unlink(os.path.join(self.jardir, dlname))
                self.logger.info('> Done in %.2f seconds' % (time.time() - serverdltime))
        else:
            self.logger.info('> Make sure to copy version jars into jars folder!')

    def download(self, url, dst):
        # Because legacy code is stupid.
        try:
            self.logger.debug("> Downloading \"" + url + "\"...")
            response = urllib.request.urlopen(url)
            data = response.read()
            with open(dst, "wb") as file:
                file.write(data)

            self.logger.debug("> Done!")
        except:
            traceback.print_exc()
            print("> Unable to download \"" + url + "\"")

    def copydir(self, src, dst, replace=True):
        """
        Shutil's built in copytree function raises an exception if src exists.
        This is basically copytree minus the exceptions and added logging.
        :param src:
        :param dst:
        :param replace:
        :return:
        """
        for file in os.listdir(src):
            if os.path.isfile(os.path.join(src, file)):
                if os.path.exists(os.path.join(dst, file)) and not replace:
                    self.logger.debug("> Skipped file \"" + os.path.join(src, file) + "\": Already exists.")
                elif os.path.exists(os.path.join(dst, file)):
                    os.unlink(os.path.join(dst, file))
                    shutil.copy2(os.path.join(src, file), dst)
                    self.logger.debug("> Replaced file \"" + os.path.join(src, file) + "\".")
                else:
                    shutil.copy2(os.path.join(src, file), dst)
                    self.logger.debug("> Copied file \"" + os.path.join(src, file) + "\".")
            elif os.path.isdir(os.path.join(dst, file)):
                self.copydir(os.path.join(src, file), os.path.join(dst, file))
            else:
                os.makedirs(os.path.join(dst, file))
                self.copydir(os.path.join(src, file), os.path.join(dst, file))

    def readconf(self):
        """
        Reads config and creates a class from it.
        Code copied from commands.py:126
        :return:
        """
        config = configparser.ConfigParser()
        with open(self._default_config) as config_file:
            config.read_file(config_file)
        if self.conffile is not None:
            config.read(self.conffile)
        self.config = config

    def writeCommand(self, command):
        if os.path.exists("runtime/command"):
            os.unlink("runtime/command")

        with open("runtime/command", "w") as file:
            file.write(command)


if __name__ == '__main__':
    installmc = InstallMC()

    if sys.argv.__len__() == 2:
        if sys.argv[1] == "scriptsonly":
            installmc.start(True)
        else:
            installmc.writeCommand(sys.argv[1])
            installmc.start()
    elif sys.argv.__len__() == 3:
        installmc.writeCommand(sys.argv[2])
        installmc.start(True)
    else:
        installmc.start()
