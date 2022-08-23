# compatible with both Python 2 and Python 3

import sys
import pefile 
import marshal
import os
import platform
import re
from .magic import magic_word_to_version
from .utilities import pyc2py, writepyc
from .pyinstxtractor import PyInstArchive
from .clean import clean

if not os.path.exists("output"):
    os.mkdir("output")

try:
    FileNotFoundError
except NameError:
    FileNotFoundError = IOError

pythonVersion = platform.python_version()

def get_rsrc(pe, name):
    for resource_type in pe.DIRECTORY_ENTRY_RESOURCE.entries:
        if str(resource_type.name) != name :
            continue
        for resource_id in resource_type.directory.entries: 
            if not hasattr(resource_id, 'directory'):
                continue
            entry = resource_id.directory.entries[0]
            rsrc = pe.get_data(entry.data.struct.OffsetToData, entry.data.struct.Size)
            return rsrc 
    return None

def check_py2exe_pyversion(pe):
    peVersion = re.findall(b"python[0-9][0-9]", pe.__data__)
    if len(set(peVersion)) == 1:
        exeVersion = '.'.join(c for c in str(peVersion[0]) if c.isdigit())
        if not pythonVersion.startswith(exeVersion):
            message = "Python {} required".format(exeVersion)
            print(message)
            print("[!] Please switch your Python version")
            return False, message
        else:
            print("Exe compiled using Python {}".format(exeVersion))
            return True, None
    else:
        if not pythonVersion.startswith('2'):
            message = "Python 2 required"
            print(message)
            print("[!] Please switch your Python version")
            return False, message
        else:
            print("Exe probably compiled using Python 2")
            return True, None

def exe2py(filename):
    pe = pefile.PE(filename)
    try:
        pe.DIRECTORY_ENTRY_RESOURCE
    except AttributeError:
        print("[!] {} is not compiled from Python".format(filename))
        return False, "Exe file not compiled from Python"
        
    # py2exe
    # adapted from https://www.mandiant.com/resources/deobfuscating-python
    rsrc = get_rsrc(pe, "PYTHONSCRIPT")
    if rsrc != None and rsrc[:4] == b"\x12\x34\x56\x78":
        print("{} compiled with py2exe".format(filename))
        correctVersion, message = check_py2exe_pyversion(pe)
        if not correctVersion:
            return False, message
        offset = rsrc[0x010:].find(b"\x00") 
        if offset >= 0:
            data = rsrc[0x10 + offset + 1:]
            py2exeCode = marshal.loads(data)[-1]
            cleanCode = clean(py2exeCode)

            pycfilename = py2exeCode.co_filename + 'c'
            try:
                writepyc(pycfilename, marshal.dumps(cleanCode))
                pyc2py(pycfilename, py2exeCode.co_filename)
            finally:
                os.remove(pycfilename)
            print("Successfully decompiled file at output/{}".format(py2exeCode.co_filename))
            return True, py2exeCode.co_filename
        else:
            print("[!] Failed to find end of header")
            return False, "Failed to find end of py2exe header"
    
    # pyinstaller
    arch = PyInstArchive(filename)
    if arch.open():
        if arch.checkFile():
            print("{} compiled with pyinstaller".format(filename))
            pyinstallerCheck, message = arch.getCArchiveInfo()
            if pyinstallerCheck == 1:
                arch.parseTOC()
                totalsuccess, files = arch.extractFiles()
                arch.close()
                return totalsuccess, files
            elif pyinstallerCheck == -1:
                # Wrong python version
                return False, message
            else:
                # Not a pyinstaller file
                pass
        arch.close()

    # cx_freeze
    if re.search(b"Unable to change DLL search path", pe.__data__):
        print("{} compiled with cx_freeze.".format(filename))
        print("[!] Run uncompyle6 on every file ending with _main_.pyc in lib\library.zip")
        return True, "[!] Manual decompilation required"

    # others
    print("[!] {} is possibly compiled from Python, but not with py2exe, pyinstaller or cx_freeze".format(filename))
    return False, "Unknown Python library used"

def decompile_exe(filename):
    try:
        with open(filename, 'rb') as f:
            magic = f.read(2)
            if magic == b'MZ':
                # exe file
                print("{} is an exe file".format(filename))
                return exe2py(filename)

            try:
                pycVersion = magic_word_to_version(magic)
                # pyc file
                print("{} is a pyc file".format(filename))
                if pycVersion == sys.version_info[0:2]:
                    pyc2py(filename, "decompiled.py")
                    print("Successfully decompiled file at output/decompiled.py")
                    return True, "decompiled.py"
                versionRequied = "Python {}.{} required".format(pycVersion[0], pycVersion[1])
                print(versionRequied)
                print("[!] Please switch your Python version")
                return False, versionRequied

            except KeyError:
                print("[!] {} is not a exe or pyc file".format(filename))
                return False, "Not exe or pyc file"

    except FileNotFoundError:
        print("[!] File {} not found".format(filename))
        return False, "File not found"
    except KeyboardInterrupt:
            print("\n [!] Terminated by user")
            sys.exit()
    except Exception as e:
        print(e)
        print("[!] Unable to bypass obfuscation for {}".format(filename))
        return False, "Unable to bypass obfuscation"