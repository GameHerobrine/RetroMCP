# -*- coding: utf-8 -*-
"""
Created on Fri Apr  8 16:36:26 2011

@author: ProfMobius & Searge
@version: v1.2
"""
import fnmatch
import warnings
import sys
import logging
import os
import shutil
import zipfile
import glob
import csv
import re
import subprocess
import configparser
import urllib.request
from hashlib import md5
from textwrap import TextWrapper  # RetroMCP
sys.path.append(os.path.dirname(os.path.realpath(__file__)))  # Workaround for python 3.6's obtuse import system.
from filehandling.srgsexport import writesrgsfromcsvs
from filehandling.srgsexport import writesrgsfromcsvnames
from pylibs.annotate_gl_constants import annotate_file
from pylibs.whereis import whereis

warnings.simplefilter('ignore')


# noinspection PyAttributeOutsideInit,PyUnboundLocalVariable
class Commands(object):
    """Contains the commands and initialisation for a full mcp run"""

    MCPVersion = '1.5'
    _instance = None  # Small trick to create a singleton
    _single = False  # Small trick to create a singleton
    _default_config = 'conf/mcp.cfg'
    _version_config = 'conf/version.cfg'
    
    @classmethod
    def fullversion(cls):
        """Read the version configuration file and return a full version string"""
        full_version = None
        try:
            config = configparser.SafeConfigParser()
            with open(os.path.normpath(cls._version_config)) as fh:
                config.readfp(fh)
            client_version = config.get('VERSION', 'ClientVersion')
            server_version = None
            try:
                server_version = config.get('VERSION', 'ServerVersion')
            except configparser.Error:
                pass
            full_version = ' (client: %s, server: %s)' % (client_version, server_version)
        except IOError:
            pass
        except configparser.Error:
            pass

        if full_version is None:
            return cls.MCPVersion
        else:
            return cls.MCPVersion + full_version

    def __init__(self, conffile=None):
        # HINT: This is for the singleton pattern. If we already did __init__, we skip it
        if Commands._single:
            return
        if not Commands._single:
            Commands._single = True

        if sys.version_info[0] < 3:
            print('ERROR : Python versions lower than 3 are not supported.')
            sys.exit(1)

        self.conffile = conffile

        self.readconf()
        self.checkfolders()

        self.startlogger()

        self.logger.info('== RetroMCP v%s ==' % Commands.fullversion())

        if 'linux' in sys.platform:
            self.osname = 'linux'
        elif 'darwin' in sys.platform:
            self.osname = 'osx'
        elif sys.platform[0:3] == 'win':
            self.osname = 'win'
        else:
            self.logger.error('OS not supported : %s' % sys.platform)
            sys.exit(0)

        self.logger.debug('OS : %s' % sys.platform)
        self.checkjava()
        self.readcommands()

    # HINT: This is for the singleton pattern. We either create a new instance or return the current one
    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Commands, cls).__new__(cls)
        return cls._instance

    def readcommands(self):
        self.patcher = self.config.get('COMMANDS', 'Patcher').replace('/', os.sep).replace('\\', os.sep)
        self.cmdpatch = self.config.get('COMMANDS', 'CmdPatch%s' % self.osname).replace('/', os.sep).replace('\\',
                                                                                                             os.sep)
        self.fernflower = self.config.get('COMMANDS', 'Fernflower').replace('/', os.sep).replace('\\', os.sep)
        self.exceptor = self.config.get('COMMANDS', 'Exceptor').replace('/', os.sep).replace('\\', os.sep)
        self.specialsource = self.config.get('COMMANDS', 'SpecialSource').replace('/', os.sep).replace('\\', os.sep)

        self.cmdrecompclt = self.config.get('COMMANDS', 'CmdRecompClt', raw=1) % self.cmdjavac
        self.cmdrecompsrv = self.config.get('COMMANDS', 'CmdRecompSrv', raw=1) % self.cmdjavac
        self.cmdstartsrv = self.config.get('COMMANDS', 'CmdStartSrv', raw=1) % self.cmdjava
        self.cmdstartclt = self.config.get('COMMANDS', 'CmdStartClt', raw=1) % self.cmdjava
        self.cmdfernflower = self.config.get('COMMANDS', 'CmdFernflower', raw=1) % self.cmdjava
        self.cmdexceptor = self.config.get('COMMANDS', 'CmdExceptor', raw=1) % self.cmdjava
        self.cmdspecialsource = self.config.get('COMMANDS', 'CmdSpecialSource', raw=1) % self.cmdjava

    def startlogger(self):
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
        formatterfile = logging.Formatter('%(asctime)s - %(module)11s.%(funcName)s - %(levelname)s - %(message)s',
                                          datefmt='%Y-%m-%d %H:%M')
        fh.setFormatter(formatterfile)
        eh.setFormatter(formatterfile)
        # add the handlers to logger
        self.logger.addHandler(ch)
        self.logger.addHandler(fh)
        self.logger.addHandler(eh)

        # HINT: SECONDARY LOGGER FOR CLIENT & SERVER
        self.loggermc = logging.getLogger('MCRunLog')
        self.loggermc.setLevel(logging.DEBUG)
        chmc = logging.StreamHandler()
        chmc.setLevel(logging.DEBUG)
        formatterconsolemc = logging.Formatter('[%(asctime)s] %(message)s', datefmt='%H:%M')
        chmc.setFormatter(formatterconsolemc)
        # add the handlers to logger
        self.loggermc.addHandler(chmc)

    def readconf(self):
        """Read the configuration file to setup some basic paths"""
        config = configparser.ConfigParser()
        with open(self._default_config) as config_file:
            config.read_file(config_file)
        if self.conffile is not None:
            config.read(self.conffile)
        self.config = config

        # HINT: We read the directories for cleanup
        try:
            self.dirtemp = config.get('DEFAULT', 'DirTemp')
            self.dirsrc = config.get('DEFAULT', 'DirSrc')
            self.dirlogs = config.get('DEFAULT', 'DirLogs')
            self.dirbin = config.get('DEFAULT', 'DirBin')
            self.dirjars = config.get('DEFAULT', 'DirJars')
            self.dirreobf = config.get('DEFAULT', 'DirReobf')
            self.dirlib = config.get('DEFAULT', 'DirLib')
            self.dirffout = config.get('DEFAULT', 'DirFFOut')
        except configparser.NoOptionError:
            pass

        # HINT: We read the position of the CSV files
        self.csvclasses = config.get('CSV', 'Classes')
        self.csvmethods = config.get('CSV', 'Methods')
        self.csvfields = config.get('CSV', 'Fields')

        # HINT: We read the names of the SRG output
        self.rgsrgsclient = config.get('SRGS', 'RGClient')
        self.rgsrgsserver = config.get('SRGS', 'RGServer')
        self.rosrgsclient = config.get('SRGS', 'ROClient')
        self.rosrgsserver = config.get('SRGS', 'ROServer')

        # HINT: We read the position of the jar files
        self.dirnatives = config.get('JAR', 'DirNatives')
        self.jarclient = config.get('JAR', 'Client')
        self.jarserver = config.get('JAR', 'Server')

        # HINT: We read keys relevant to retroguard
        self.rgclientout = config.get('OBFUSCATE', 'ClientOut')
        self.rgserverout = config.get('OBFUSCATE', 'ServerOut')

        # HINT: We read keys relevant to exceptor
        self.xclientconf = config.get('EXCEPTOR', 'XClientCfg')
        self.xserverconf = config.get('EXCEPTOR', 'XServerCfg')
        self.xclientout = config.get('EXCEPTOR', 'XClientOut')
        self.xserverout = config.get('EXCEPTOR', 'XServerOut')
        self.xclientlog = config.get('EXCEPTOR', 'XClientLog')
        self.xserverlog = config.get('EXCEPTOR', 'XServerLog')

        # HINT: We read keys relevant to fernflower
        self.ffclientconf = config.get('DECOMPILE', 'FFClientConf')
        self.ffserverconf = config.get('DECOMPILE', 'FFServerConf')
        self.ffclientout = config.get('DECOMPILE', 'FFClientOut')
        self.ffserverout = config.get('DECOMPILE', 'FFServerOut')
        self.ffclientsrc = config.get('DECOMPILE', 'FFClientSrc')
        self.ffserversrc = config.get('DECOMPILE', 'FFServerSrc')
        self.ffsource = config.get('DECOMPILE', 'FFSource')

        # HINT: We read the output directories
        self.binouttmp = config.get('OUTPUT', 'BinOut')
        self.binclienttmp = config.get('OUTPUT', 'BinClient')
        self.binservertmp = config.get('OUTPUT', 'BinServer')
        self.srcclient = config.get('OUTPUT', 'SrcClient')
        self.srcserver = config.get('OUTPUT', 'SrcServer')

        # HINT: Patcher related configs
        self.patchtemp = config.get('PATCHES', 'PatchTemp')
        self.patchclient = config.get('PATCHES', 'PatchClient')
        self.patchserver = config.get('PATCHES', 'PatchServer')

        # HINT: Recompilation related configs
        try:
            self.binclient = config.get('RECOMPILE', 'BinClient')
            self.binserver = config.get('RECOMPILE', 'BinServer')
            self.cpathclient = config.get('RECOMPILE', 'ClassPathClient').split(',')
            self.fixesclient = config.get('RECOMPILE', 'ClientFixes')
            self.cpathserver = config.get('RECOMPILE', 'ClassPathServer').split(',')
            self.fixesserver = config.get('RECOMPILE', 'ServerFixes')
        except configparser.NoOptionError:
            pass

        # HINT: Reobf related configs
        self.md5client = config.get('REOBF', 'MD5Client')
        self.md5server = config.get('REOBF', 'MD5Server')
        self.md5reobfclient = config.get('REOBF', 'MD5PreReobfClient')
        self.md5reobfserver = config.get('REOBF', 'MD5PreReobfServer')
        self.reobsrgclient = config.get('REOBF', 'ObfSRGClient')
        self.reobsrgserver = config.get('REOBF', 'ObfSRGServer')
        self.cmpjarclient = config.get('REOBF', 'RecompJarClient')
        self.cmpjarserver = config.get('REOBF', 'RecompJarServer')
        self.reobfjarclient = config.get('REOBF', 'ObfJarClient')
        self.reobfjarserver = config.get('REOBF', 'ObfJarServer')
        self.nullpkg = config.get('REOBF', 'NullPkg')
        self.ignorepkg = config.get('REOBF', 'IgnorePkg').split(',')
        self.dirreobfclt = config.get('REOBF', 'ReobfDirClient')
        self.dirreobfsrv = config.get('REOBF', 'ReobfDirServer')

        self.mcplogfile = config.get('MCP', 'LogFile')
        self.mcperrlogfile = config.get('MCP', 'LogFileErr')
        
        self.md5jarclt = None
        self.md5jarsrv = None
        self.proxyport = None
        try:
            config = configparser.SafeConfigParser()
            with open(self._version_config) as fh:
                config.readfp(fh)
            self.md5jarclt = config.get('VERSION', 'MD5Client').split(',')
            self.md5jarsrv = config.get('VERSION', 'MD5Server').split(',')
            self.proxyport = config.get('VERSION', 'ProxyPort')
        except IOError:
            pass
        except configparser.Error:
            pass

    def hasserver(self):
        return len(self.md5jarsrv)
    
    def createsrgs(self, side):
        """Write the srgs files."""
        sidelk = {0: self.rgsrgsclient, 1: self.rgsrgsserver}
        writesrgsfromcsvs(self.csvclasses, self.csvmethods, self.csvfields, sidelk[side], side)

    def createsrgsforreobf(self, side):
        """Write the srgs files."""
        srclk = {0: self.dirtemp + "/client_recomp.jar", 1: self.dirtemp + "/server_recomp.jar"}
        sidelk = {0: self.reobsrgclient, 1: self.reobsrgserver}
        writesrgsfromcsvnames(self.csvclasses, self.csvmethods, self.csvfields, sidelk[side], side)

        existingclasses = self.parsesrgforclasses(sidelk[side])
        with open(sidelk[side], "r") as file:
            text = file.read()
        text += self.generatesrgfornewclasses(srclk[side], existingclasses)
        with open(sidelk[side], "w") as file:
            file.write(text)

    def parsesrgforclasses(self, srg):
        classes = []
        with open(srg, "r") as file:
            for line in file:
                if line.startswith("CL: "):
                    entry = line.split(" ")
                    classes.append(entry[1])

        return classes

    def generatesrgfornewclasses(self, jarpath, existingclasses):
        with zipfile.ZipFile(jarpath, "r") as zipjar:
            text = ""
            for file in zipjar.namelist():
                if file.endswith(".class"):
                    file = file[:-6]
                if file not in existingclasses and not file.__contains__(" ") and file.startswith("net/minecraft/src"):
                    print("Found new class: \"" + file + "\", adding to SRG.")
                    text += "\n\nCL: " + file + " " + file.split("net/minecraft/src/")[-1]
        return text

    def checkjava(self):
        """Check for java and setup the proper directory if needed"""
        results = []
        if self.osname == 'win':
            if subprocess.call('javac.exe 1>NUL 2>NUL', shell=True) == 2:
                self.cmdjava = 'java.exe'
                self.cmdjavac = 'javac.exe'
                return
            else:
                import winreg
                for flag in [winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY]:
                    try:
                        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, "Software\\JavaSoft\\Java Development Kit", 0,
                                            winreg.KEY_READ | flag)
                        version, _ = winreg.QueryValueEx(k, "CurrentVersion")
                        k.Close()
                        k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                            "Software\\JavaSoft\\Java Development Kit\\%s" % version, 0,
                                            winreg.KEY_READ | flag)
                        path, _ = winreg.QueryValueEx(k, "JavaHome")
                        k.Close()
                        if subprocess.call('"%s" 1>NUL 2>NUL' % os.path.join(path, "bin", "javac.exe"),
                                           shell=True) == 2:
                            self.cmdjava = '"%s"' % os.path.join(path, "bin", "java.exe")
                            self.cmdjavac = '"%s"' % os.path.join(path, "bin", "javac.exe")
                            return
                    except OSError:
                        pass

                if 'ProgramW6432' in os.environ:
                    results.extend(whereis('javac.exe', os.environ['ProgramW6432']))
                if 'ProgramFiles' in os.environ:
                    results.extend(whereis('javac.exe', os.environ['ProgramFiles']))
                if 'ProgramFiles(x86)' in os.environ:
                    results.extend(whereis('javac.exe', os.environ['ProgramFiles(x86)']))

        if self.osname in ['linux', 'osx']:
            if subprocess.call('javac 1> /dev/null 2> /dev/null', shell=True) == 2:
                self.cmdjava = 'java'
                self.cmdjavac = 'javac'
                return
            else:
                results.extend(whereis('javac', '/usr/bin'))
                results.extend(whereis('javac', '/usr/local/bin'))
                results.extend(whereis('javac', '/opt'))

        if not results:
            self.logger.error('Java SDK is not installed ! Please install java SDK from ???')
            sys.exit(0)
        else:
            if self.osname == 'win':
                self.cmdjavac = '"%s"' % os.path.join(results[0], 'javac.exe')
                self.cmdjava = '"%s"' % os.path.join(results[0], 'java.exe')
            if self.osname in ['linux', 'osx']:
                self.cmdjavac = os.path.join(results[0], 'javac')
                self.cmdjava = os.path.join(results[0], 'java')

    def checkjars(self, side):
        jarlk = {0: self.jarclient, 1: self.jarserver}
        md5jarlk = {0: self.md5jarclt, 1: self.md5jarsrv}

        if not os.path.exists(jarlk[side]):
            self.logger.warning('!! Missing jar file %s. Aborting !!' % jarlk[side])
            return False

        with open(jarlk[side], 'rb') as jar_file:
            md5jar = md5(jar_file.read()).hexdigest()

        validjar = False
        for x in md5jarlk[side]:
            if x == md5jar or x == "any":
                validjar = True
        
        if not validjar:
            self.logger.warning('!! Modified jar detected. Unpredictable results !!')
            self.logger.debug('md5: ' + md5jar)

        return True

    def checksources(self, side):
        srclk = {0: self.srcclient, 1: self.srcserver}
        if side == 0:
            if not os.path.exists(os.path.join(srclk[side], 'net/minecraft/client/Minecraft.java')) and not os.path.exists(os.path.join(srclk[side], 'com/mojang/minecraft/Minecraft.java')) and not os.path.exists(os.path.join(srclk[side], 'net/minecraft/src/Minecraft.java')) and not os.path.exists(os.path.join(srclk[side], 'com/mojang/rubydung/RubyDung.java')) and not os.path.exists(os.path.join(srclk[side], 'com/mojang/minecraft/RubyDung.java')):
                self.logger.warning('!! Can not find client sources !!')
                return False
            else:
                return True

        if side == 1:
            if not os.path.exists(os.path.join(srclk[side], 'net/minecraft/server/MinecraftServer.java')) and not os.path.exists(os.path.join(srclk[side], 'com/mojang/minecraft/server/MinecraftServer.java')):
                self.logger.warning('!! Can not find server sources !!')
                return False
            else:
                return True

    def checkbins(self, side):
        binlk = {0: self.binclient, 1: self.binserver}
        if side == 0:
            if not os.path.exists(os.path.join(binlk[side], 'net/minecraft/client/Minecraft.class')) and not os.path.exists(os.path.join(binlk[side], 'com/mojang/minecraft/Minecraft.class')) and not os.path.exists(os.path.join(binlk[side], 'net/minecraft/src/Minecraft.class')) and not os.path.exists(os.path.join(binlk[side], 'com/mojang/rubydung/RubyDung.class')) and not os.path.exists(os.path.join(binlk[side], 'com/mojang/minecraft/RubyDung..class')):
                self.logger.warning('!! Can not find client bins !!')
                return False
            else:
                return True

        if side == 1:
            if not os.path.exists(os.path.join(binlk[side], 'net/minecraft/server/MinecraftServer.class')) and not os.path.exists(os.path.join(binlk[side], 'com/mojang/minecraft/server/MinecraftServer.class')):
                self.logger.warning('!! Can not find server bins !!')
                return False
            else:
                return True

    def checkfolders(self):
        try:
            if not os.path.exists(self.dirtemp):
                os.mkdir(self.dirtemp)
            if not os.path.exists(self.dirsrc):
                os.mkdir(self.dirsrc)
            if not os.path.exists(self.dirlogs):
                os.mkdir(self.dirlogs)
            if not os.path.exists(self.dirbin):
                os.mkdir(self.dirbin)
            if not os.path.exists(self.dirreobf):
                os.mkdir(self.dirreobf)
            if not os.path.exists(self.dirlib):
                os.mkdir(self.dirlib)
        except AttributeError:
            pass

    # Check for updates
    def checkforupdates(self, silent=False):
        # Disabled due to an issue with configparser.
        try:
            url = urllib.request.urlopen('https://raw.githubusercontent.com/MCPHackers/RetroMCP/master/mcpversion.txt')
            content = url.read().decode("UTF-8")

            self.latestversion = content

            self.logger.debug('Current version: ' + Commands.MCPVersion)
            self.logger.debug('Latest version: ' + self.latestversion)
        except IOError:
            self.logger.error('Could not fetch the latest version!')
            return False

        if Commands.MCPVersion != self.latestversion:
            if not silent:
                self.logger.info(
                    'MCP version ' + self.latestversion + ' has been released! Run updatemcp.bat to download it!')
            result = True
        else:
            result = False
        return result

    def cleanbindirs(self, side):
        pathbinlk = {0: self.binclient, 1: self.binserver}

        for path, dirlist, filelist in os.walk(pathbinlk[side]):
            for bin_file in glob.glob(os.path.join(path, '*.class')):
                os.remove(bin_file)

    def cleanreobfdir(self, side):
        outpathlk = {0: self.dirreobfclt, 1: self.dirreobfsrv}
        pathbinlk = {0: self.binclient, 1: self.binserver}
        if os.path.exists(outpathlk[side]):
            shutil.rmtree(outpathlk[side], ignore_errors=True)

        shutil.copytree(pathbinlk[side], outpathlk[side])
        for path, dirlist, filelist in os.walk(outpathlk[side]):
            for bin_file in glob.glob(os.path.join(path, '*.class')):
                os.remove(bin_file)

        for i in range(4):
            for path, dirlist, filelist in os.walk(outpathlk[side]):
                if not dirlist and not filelist:
                    shutil.rmtree(path)

        if not os.path.exists(outpathlk[side]):
            os.mkdir(outpathlk[side])

    def applyff(self, side):
        """Apply fernflower to the given side"""

        if side == 0:
            ffconf = self.ffclientconf
            ffsrc = self.xclientout

        if side == 1:
            ffconf = self.ffserverconf
            ffsrc = self.xserverout

        if not os.path.exists(self.dirffout):
            os.makedirs(self.dirffout)

        forkcmd = self.cmdfernflower.format(jarff=self.fernflower, conf=ffconf, jarin=ffsrc, jarout=self.dirffout)
        self.runcmd(forkcmd)

    def applyexceptor(self, side):
        """Apply exceptor to the given side"""
        excinput = {0: self.rgclientout, 1: self.rgserverout}
        excoutput = {0: self.xclientout, 1: self.xserverout}
        excconf = {0: self.xclientconf, 1: self.xserverconf}
        exclog = {0: self.xclientlog, 1: self.xserverlog}

        forkcmd = self.cmdexceptor.format(jarexc=self.exceptor, input=excinput[side], output=excoutput[side],
                                          conf=excconf[side], log=exclog[side])
        self.runcmd(forkcmd)

    def applyss(self, side):
        if side == 0:
            ssinputjar = self.jarclient
            ssoutputjar = self.rgclientout
            srgfile = self.rgsrgsclient

        if side == 1:
            ssinputjar = self.jarserver
            ssoutputjar = self.rgserverout
            srgfile = self.rgsrgsserver

        forkcmd = self.cmdspecialsource.format(jarexc=self.specialsource, input=ssinputjar, output=ssoutputjar,
                                               srg=srgfile)
        self.runcmd(forkcmd)

    def applyffpatches(self, side):
        """Applies the patches to the src directory"""
        pathsrclk = {0: self.srcclient, 1: self.srcserver}
        patchlk = {0: self.patchclient, 1: self.patchserver}

        # HINT: Here we transform the patches to match the directory separator of the specific platform
        with open(self.patchtemp, 'w') as outpatch, open(patchlk[side], 'r') as patch_file:
            patch = patch_file.read().splitlines()
            for line in patch:
                if line[:3] in ['+++', '---', 'Onl', 'dif']:
                    outpatch.write(line.replace('\\', os.sep).replace('/', os.sep) + '\r\n')
                else:
                    outpatch.write(line + '\r\n')

        forkcmd = self.cmdpatch.format(srcdir=pathsrclk[side], patchfile=self.patchtemp)

        p = subprocess.Popen(forkcmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        linebuffer = []
        errormsgs = []
        retcode = None
        errored = False
        while True:
            if not errored:
                try:
                    o = p.stdout.readline().decode(sys.stdout.encoding)
                except:
                    self.logger.warning("Failed to log program output! Program is still running, but will not be logged.")
                    errored = True
            retcode = p.poll()
            if retcode is not None:
                break
            if not errored and o != '':
                linebuffer.append(o.strip())

        if retcode == 0:
            for line in linebuffer:
                self.logger.debug(line)
        else:
            self.logger.warning('%s failed.' % forkcmd)
            self.logger.warning('Return code : %d' % retcode)
            for line in linebuffer:
                if 'saving rejects' in line:
                    errormsgs.append(line)
                self.logger.debug(line)

            self.logger.warning('')
            self.logger.warning('== ERRORS FOUND ==')
            self.logger.warning('')
            for line in errormsgs:
                self.logger.warning(line)
            self.logger.warning('==================')
            self.logger.warning('')

    def recompile(self, side):
        """Recompile the sources and produce the final bins"""
        cmdlk = {0: self.cmdrecompclt, 1: self.cmdrecompsrv}
        pathbinlk = {0: self.binclient, 1: self.binserver}
        pathsrclk = {0: self.srcclient, 1: self.srcserver}

        if not os.path.exists(pathbinlk[side]):
            os.mkdir(pathbinlk[side])

        # HINT: We create the list of source directories based on the list of packages
        self.logger.info("> Gathering class list.")
        pkglist = ""
        for path, dirlist, filelist in os.walk(pathsrclk[side]):
            globlist = glob.glob(os.path.join(path, '*.java'))
            for file in globlist:
                pkglist += os.path.join(file) + '\n'
        with open(self.dirtemp + "/recompclasslist.txt", "w") as file:
            file.write(pkglist)
        
        forkcmd = ''
        cp = ''
        fixesforside = None
        if side == 0:
            cp = os.pathsep.join(self.cpathclient)
            fixesforside = self.fixesclient

        if side == 1:
            cp = os.pathsep.join(self.cpathserver)
            fixesforside = self.fixesserver
        forkcmd = cmdlk[side].format(classpath=cp, sourcepath=pathsrclk[side], outpath=pathbinlk[side], pkgs="@temp/recompclasslist.txt", fixes=fixesforside)

        self.logger.debug("recompile: '" + forkcmd + "'")
        p = subprocess.Popen(forkcmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        linebuffer = []
        errormsgs = []
        retcode = None
        errored = False
        while True:
            if not errored:
                try:
                    o = p.stdout.readline().decode(sys.stdout.encoding)
                except:
                    self.logger.warning("Failed to log program output! Program is still running, but will not be logged.")
                    errored = True
            retcode = p.poll()
            if retcode is not None:
                break
            if not errored and o != '':
                linebuffer.append(o.strip())

        if retcode == 0:
            for line in linebuffer:
                self.logger.debug(line)
        else:
            self.logger.error('%s failed.' % forkcmd)
            self.logger.error('Return code : %d' % retcode)
            for line in linebuffer:
                if not line.strip():
                    continue
                if line[0] != '[' and line[0:4] != 'Note':
                    errormsgs.append(line)
                self.logger.debug(line)

            self.logger.error('')
            self.logger.error('== ERRORS FOUND ==')
            self.logger.error('')
            for line in errormsgs:
                self.logger.error(line)
                if '^' in line:
                    self.logger.error('')
            self.logger.error('==================')
            self.logger.error('')
            # sys.exit(1)

    def startserver(self):
        cps = ['../' + p for p in self.cpathserver]
        cps.insert(2, '../' + self.binserver)
        cps = os.pathsep.join(cps)
        # self.logger.info("classpath: '"+cps+"'")

        os.chdir(self.dirjars)

        forkcmd = self.cmdstartsrv.format(classpath=cps, proxyport=self.proxyport)
        self.runmc(forkcmd)

    def startclient(self):
        cpc = ['../' + p for p in self.cpathclient]
        cpc.insert(2, '../' + self.binclient)
        cpc = os.pathsep.join(cpc)
        # self.logger.info("classpath: '"+cpc+"'")

        os.chdir(self.dirjars)

        forkcmd = self.cmdstartclt.format(classpath=cpc, natives='../' + self.dirnatives, proxyport=self.proxyport)
        self.runmc(forkcmd)

    def runcmd(self, forkcmd):
        self.logger.debug("runcmd: '" + forkcmd + "'")
        p = subprocess.Popen(forkcmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        linebuffer = []
        errored = False
        while True:
            if not errored:
                try:
                    o = p.stdout.readline().decode(sys.stdout.encoding)
                except:
                    self.logger.warning("Failed to log program output! Program is still running, but will not be logged.")
                    errored = True
            retcode = p.poll()
            if retcode is not None:
                break
            if not errored and o != '':
                linebuffer.append(o.strip())

        if retcode == 0:
            for line in linebuffer:
                self.logger.debug(line)
        else:
            self.logger.error('%s failed.' % forkcmd)
            self.logger.error('Return code : %d' % retcode)
            for line in linebuffer:
                self.logger.error(line)
        return retcode

    def runmc(self, forkcmd):
        self.logger.debug("runmc: '" + forkcmd + "'")
        pclient = subprocess.Popen(forkcmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        msgs = []
        errored = False
        while True:
            if not errored:
                try:
                    o = pclient.stdout.readline().decode(sys.stdout.encoding)
                except:
                    self.logger.warning("Failed to log program output! Program is still running, but will not be logged.")
                    errored = True
            returnvalue = pclient.poll()
            if returnvalue is not None:
                break
            if not errored and o != '':
                self.loggermc.debug(o.strip())
                msgs.append(o.strip())

        if returnvalue == 0:
            for line in msgs:
                self.logger.debug(line)
        else:
            self.logger.error('%s failed.' % forkcmd)
            self.logger.error('Return code : %d' % returnvalue)
            for line in msgs:
                self.logger.error(line)

        return returnvalue

    def extractjar(self, side):
        """Unzip the jar file to the bin directory defined in the config file"""
        pathbinlk = {0: self.binclienttmp, 1: self.binservertmp}
        jarlk = {0: self.xclientout, 1: self.xserverout}

        # HINT: We check if the top output directory exists. If not, we create it
        # We than check if the specific side directory exists. If it does, we delete it and create a new one
        if not os.path.exists(self.binouttmp):
            os.mkdir(self.binouttmp)
        if os.path.exists(pathbinlk[side]):
            shutil.rmtree(pathbinlk[side])
        os.mkdir(pathbinlk[side])

        # HINT: We extract the jar to the right location
        zipjar = zipfile.ZipFile(jarlk[side])
        zipjar.extractall(pathbinlk[side])

    def extractsrc(self, side):
        """Unzip the source jar file to the src directory defined in the config file"""
        pathbinlk = {0: self.ffclientout, 1: self.ffserverout}
        jarlk = {0: self.ffclientsrc, 1: self.ffserversrc}
        pathsrclk = {0: self.srcclient, 1: self.srcserver}

        # HINT: We check if the top output directory exists. If not, we create it
        if not os.path.exists(pathbinlk[side]):
            os.makedirs(pathbinlk[side])

        # HINT: We extract the jar to the right location
        zipjar = zipfile.ZipFile(jarlk[side])
        zipjar.extractall(pathbinlk[side])

        self.copyandfixsrc(pathbinlk[side], pathsrclk[side])

    def copyandfixsrc(self, src_dir, dest_dir):
        src_dir = os.path.normpath(src_dir)
        dest_dir = os.path.normpath(dest_dir)

        for path, dirlist, filelist in os.walk(src_dir):
            sub_dir = os.path.relpath(path, src_dir)
            if sub_dir == '.':
                sub_dir = ''

            for cur_dir in dirlist:
                if os.path.join(sub_dir, cur_dir).replace(os.sep, '/') in self.ignorepkg:
                    # if the full subdir is in the ignored package list delete it so that we don't descend into it
                    dirlist.remove(cur_dir)

            for cur_file in fnmatch.filter(filelist, '*.java'):
                src_file = os.path.join(src_dir, sub_dir, cur_file)
                dest_file = os.path.join(dest_dir, sub_dir, cur_file)

                if not os.path.exists(os.path.dirname(dest_file)):
                    os.makedirs(os.path.dirname(dest_file))

                # don't bother fixing line endings in windows
                if self.osname == 'win':
                    shutil.copyfile(src_file, dest_file)
                else:
                    # read each line in the file, stripping existing line end and adding dos line end
                    with open(src_file, 'r') as in_file:
                        with open(dest_file, 'w') as out_file:
                            for line in in_file:
                                out_file.write(line.rstrip() + '\r\n')

    def rename(self, side, reverse=False):
        """Rename the sources using the CSV data"""
        pathsrclk = {0: self.srcclient, 1: self.srcserver}

        # HINT: We read the relevant CSVs
        with open(self.csvmethods, 'r') as methods_file, open(self.csvfields, 'r') as fields_file:
            methodsreader = csv.DictReader(methods_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL)
            fieldsreader = csv.DictReader(fields_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL)

            methods = {}
            fields = {}
            for row in methodsreader:
                if int(row['side']) == side:
                    if row['searge'] in methods:
                        self.logger.debug('WTF ? %s' % row['searge'])
                    methods[row['searge']] = row
            for row in fieldsreader:
                if int(row['side']) == side:
                    if row['searge'] in methods:
                        self.logger.debug('WTF ? %s' % row['searge'])
                    fields[row['searge']] = row

        type_hash = {'methods': 'func', 'fields': 'field'}
        regexp_searge = r'%s_[0-9]+_[a-zA-Z]+_?'

        # HINT: We pathwalk the sources
        for path, dirlist, filelist in os.walk(pathsrclk[side]):
            for src_file in glob.glob(os.path.join(path, '*.java')):
                with open(src_file, 'r') as ff, open(src_file + '.tmp', 'w') as fftmp:
                    ffbuffer = ff.read()

                    # HINT: We check if the sources have func_????_? or field_????_? in them.
                    # If yes, we replace with the relevant information
                    for group in ['methods', 'fields']:
                        results = re.findall(regexp_searge % type_hash[group], ffbuffer)

                        for result in results:
                            # HINT: It is possible for the csv to contain data
                            # from previous version or enums, so we catch those
                            try:
                                ffbuffer = ffbuffer.replace(result, locals()[group][result]['name'])
                            except KeyError as msg:
                                self.logger.debug("Can not replace %s on side %d" % (msg, side))

                    fftmp.write(ffbuffer)

                shutil.move(src_file + '.tmp', src_file)

                # HINT: We annotate the GL constants
                annotate_file(src_file)

    def gathermd5s(self, side, reobf=False):
        if not reobf:
            md5lk = {0: self.md5client, 1: self.md5server}
        else:
            md5lk = {0: self.md5reobfclient, 1: self.md5reobfserver}
        pathbinlk = {0: self.binclient, 1: self.binserver}

        with open(md5lk[side], 'w') as md5_file:
            # HINT: We pathwalk the recompiled classes
            for path, dirlist, filelist in os.walk(pathbinlk[side]):
                for bin_file in glob.glob(os.path.join(path, '*.class')):
                    bin_file_osindep = os.sep.join(bin_file.replace(os.sep, '/').split('/')[2:]).split('.')[0]
                    with open(bin_file, 'rb') as the_class:
                        md5_file.write('%s %s\n' % (bin_file_osindep, md5(the_class.read()).hexdigest()))

    def packbin(self, side):
        jarlk = {0: self.cmpjarclient, 1: self.cmpjarserver}
        pathbinlk = {0: self.binclient, 1: self.binserver}
        pathtmpbinlk = {0: self.binclienttmp, 1: self.binservertmp}

        # HINT: We create the zipfile and add all the files from the bin directory
        zipjar = zipfile.ZipFile(jarlk[side], 'w')
        for path, dirlist, filelist in os.walk(pathbinlk[side]):
            path = path.replace('/', os.sep)
            for bin_file in glob.glob(os.path.join(path, '*.class')):
                zipjar.write(bin_file, os.sep.join(bin_file.split(os.sep)[2:]))

        for pkg in self.ignorepkg:
            curpath = os.path.join(pathtmpbinlk[0], pkg)
            for path, dirlist, filelist in os.walk(curpath):
                path = path.replace('/', os.sep)
                for bin_file in glob.glob(os.path.join(path, '*.class')):
                    zipjar.write(bin_file, os.sep.join(bin_file.split(os.sep)[3:]))

        zipjar.close()

    def reobfuscate(self, side):
        if side == 0:
            ssinput = self.cmpjarclient
            ssoutput = self.reobfjarclient
            rosrgfile = self.rosrgsclient

        if side == 1:
            ssinput = self.cmpjarserver
            ssoutput = self.reobfjarserver
            rosrgfile = self.rosrgsserver

        forkcmd = self.cmdspecialsource.format(jarexc=self.specialsource, input=ssinput, output=ssoutput, srg=rosrgfile)
        self.runcmd(forkcmd)

    def unpackreobfclasses(self, side):
        jarlk = {0: self.reobfjarclient, 1: self.reobfjarserver}
        md5lk = {0: self.md5client, 1: self.md5server}
        md5reoblk = {0: self.md5reobfclient, 1: self.md5reobfserver}
        outpathlk = {0: self.dirreobfclt, 1: self.dirreobfsrv}

        # HINT: We need a table for the old md5 and the new ones
        md5table = {}
        md5reobtable = {}

        with open(md5lk[side], 'r') as md5table_file:
            for row in md5table_file.read().splitlines():
                row = row.strip().split()
                if len(row) == 2:
                    md5table[row[0].replace(os.sep, '/')] = row[1]

        with open(md5reoblk[side], 'r') as md5reobtable_file:
            for row in md5reobtable_file.read().splitlines():
                row = row.strip().split()
                if len(row) == 2:
                    md5reobtable[row[0].replace(os.sep, '/')] = row[1]

        trgclasses = []
        for key, value in md5reobtable.items():
            if not key in md5table:
                self.logger.info('> New class found      : %s' % key)
                trgclasses.append(key.split('.')[0])
                continue
            if not md5table[key] == md5reobtable[key]:
                trgclasses.append(key.split('.')[0])
                self.logger.info('> Modified class found : %s' % key)

        with open(self.csvclasses, 'r') as classes_file:
            classesreader = csv.DictReader(classes_file, delimiter=',', quotechar='"', quoting=csv.QUOTE_ALL)
            classes = {}
            for row in classesreader:
                if int(row['side']) == side:
                    # HINT: This pkg equivalence is used to reduce the src pkg to the null one
                    pkg = row['package'] + '/'
                    if row['package'] == self.nullpkg:
                        pkg = ''
                    classes['%s/%s' % (row['package'], row['name'])] = row['notch']

        if not os.path.exists(outpathlk[side]):
            os.mkdir(outpathlk[side])

        # HINT: We extract the modified class files
        zipjar = zipfile.ZipFile(jarlk[side], 'r')
        for i in trgclasses:
            if i in classes:
                zipjar.extract('%s.class' % classes[i], outpathlk[side])
                self.logger.info('> Outputted %s to %s as %s' % (i.ljust(35), outpathlk[side], classes[i] + '.class'))
            else:
                i = i.replace(self.nullpkg, '')
                if i[0] == '/':
                    i = i[1:]
                zipjar.extract('%s.class' % i, outpathlk[side])
                self.logger.info('> Outputted %s to %s as %s' % (i.ljust(35), outpathlk[side], i + '.class'))
        zipjar.close()

    #Unused and unfinished
    def downloadupdates(self, force=False):
        newfiles = self.checkupdates(silent=True)

        if not newfiles:
            self.logger.info('No new updates found.')
            return

        for entry in newfiles:
            if entry[3] == 'U':
                self.logger.info('New version found for : %s' % entry[0])
            if entry[3] == 'D':
                self.logger.info('File tagged for deletion : %s' % entry[0])

        if 'CHANGELOG' in [i[0] for i in newfiles]:
            print('')
            self.logger.info('== CHANGELOG ==')
            changelog = urllib.request.urlopen('https://raw.githubusercontent.com/MCPHackers/RetroMCP/master/docs/Changelog.log').readlines()
            for line in changelog and not line.startswith('===='):
                self.logger.info(line.strip())
                if not line.strip():
                    break
            print('')
            print('')

        if not force:
            print('WARNING:')
            print('You are going to update MCP')
            print('Are you sure you want to continue ?')
            answer = input('If you really want to update, enter "Yes" ')
            if not answer.lower() in ['yes', 'y']:
                print('You have not entered "Yes", aborting the update process')
                sys.exit(0)

        for entry in newfiles:
            if entry[3] == 'U':
                self.logger.info('Retrieving file from server : %s' % entry[0])
                entrydir = os.path.dirname(entry[0])
                if not os.path.isdir(entrydir):
                    try:
                        os.makedirs(entrydir)
                    except OSError:
                        pass

                urllib.request.urlretrieve('http://mcp.ocean-labs.de/files/mcprolling/mcp/' + entry[0], entry[0])
            if entry[3] == 'D':
                self.logger.info('Removing file from local install : %s' % entry[0])
                # Remove file here

    # LTS Update MCP
    def updatemcp(self, force=False):
        if self.checkforupdates(silent=True):
            self.logger.info('Update found! The latest version is ' + self.latestversion + ','
                             ' and you are using ' + Commands.MCPVersion + '!')
            self.logger.info('Downloading!')

            filename = 'mcp' + self.latestversion.replace('.', '') + '.zip'
            os.system('runtime\\bin\\wget.exe -q -O ' + filename + ' http://github.com/MCPHackers/RetroMCP/archive/master.zip')
            self.logger.info('Download complete! Saved to ' + filename + '!')
            print('')
            self.logger.info('== CHANGELOG ==')
            changelog = urllib.request.urlopen('https://raw.githubusercontent.com/MCPHackers/RetroMCP/master/docs/Changelog.log').readlines()
            for line in changelog:
                l = line.decode("UTF-8")
                if l.startswith("===="):
                    break
                self.logger.info(l.strip("\n"))
                if not l:
                    break
            print('')
        else:
            self.logger.info('You are using the latest version of MCP! (' + Commands.MCPVersion + ')')

    # LTS BACKPORTED JAVADOC
    def process_javadoc(self, side):
        """Add CSV descriptions to methods and fields as javadoc"""
        pathsrclk = {0: self.srcclient, 1: self.srcserver}

        # HINT: We read the relevant CSVs
        with open(self.csvmethods, 'r') as methods_file, open(self.csvfields, 'r') as fields_file:
            methodsreader = csv.DictReader(methods_file)
            fieldsreader = csv.DictReader(fields_file)

            methods = {}
            for row in methodsreader:
                # HINT: Only include methods that have a non-empty description
                if int(row['side']) == side and 'desc' in row and row['desc']:
                    methods[row['searge']] = row['desc'].replace('*/', '* /')

            fields = {}
            for row in fieldsreader:
                # HINT: Only include fields that have a non-empty description
                if int(row['side']) == side and 'desc' in row and row['desc']:
                    fields[row['searge']] = row['desc'].replace('*/', '* /')

        regexps = {
            'field': re.compile(r'^ {4}(?:[\w$.[\]]+ )*(?P<name>field_[0-9]+_[a-zA-Z_]+) *(?:=|;)'),
            'method': re.compile(r'^ {4}(?:[\w$.[\]]+ )*(?P<name>func_[0-9]+_[a-zA-Z_]+)\('),
        }
        wrapper = TextWrapper(width=120)

        # HINT: We pathwalk the sources
        for path, _, filelist in os.walk(pathsrclk[side], followlinks=True):
            for cur_file in fnmatch.filter(filelist, '*.java'):
                src_file = os.path.normpath(os.path.join(path, cur_file))
                tmp_file = src_file + '.tmp'
                with open(src_file, 'r') as fh:
                    buf_in = fh.readlines()

                buf_out = []
                # HINT: Look for method/field declarations in this file
                for line in buf_in:
                    fielddecl = regexps['field'].match(line)
                    methoddecl = regexps['method'].match(line)
                    if fielddecl:
                        prev_line = buf_out[-1].strip()
                        indent = '    '
                        name = fielddecl.group('name')
                        if name in fields:
                            desc = fields[name]
                            if len(desc) < 70:
                                if prev_line != '' and prev_line != '{':
                                    buf_out.append('\n')
                                buf_out.append(indent + '/** ')
                                buf_out.append(desc)
                                buf_out.append(' */\n')
                            else:
                                wrapper.initial_indent = indent + ' * '
                                wrapper.subsequent_indent = indent + ' * '
                                if prev_line != '' and prev_line != '{':
                                    buf_out.append('\n')
                                buf_out.append(indent + '/**\n')
                                buf_out.append(wrapper.fill(desc) + '\n')
                                buf_out.append(indent + ' */\n')
                    elif methoddecl:
                        prev_line = buf_out[-1].strip()
                        indent = '    '
                        name = methoddecl.group('name')
                        if name in methods:
                            desc = methods[name]
                            wrapper.initial_indent = indent + ' * '
                            wrapper.subsequent_indent = indent + ' * '
                            if prev_line != '' and prev_line != '{':
                                buf_out.append('\n')
                            buf_out.append(indent + '/**\n')
                            buf_out.append(wrapper.fill(desc) + '\n')
                            buf_out.append(indent + ' */\n')
                    buf_out.append(line)

                with open(tmp_file, 'w') as fh:
                    fh.writelines(buf_out)
                shutil.move(tmp_file, src_file)
        return True
