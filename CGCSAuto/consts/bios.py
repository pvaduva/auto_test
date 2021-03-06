
class TerminalKeys:
    Keys = {
        "Enter_": '\r\r',
        "Enter": '\r',
        "Return": '\r\r',
        "Esc": '\x1b',
        "Escape": '\x1b',
        "Insert": "placeholder",
        "Del": "placeholder",
        "Delete": "placeholder",
        "Tab": "placeholder",
        "F1": '\x1b' + '[OP',
        "F2": '\x1b' + '[OQ',
        "F3": '\x1b' + '[OR',
        "F4": '\x1b' + '[OS',
        "F5": None,
        "F6": '\x1b' + '[17~',
        "F7": '\x1b' + '[18~',
        "F8": '\x1b' + '[19~',
        "F9": '\x1b' + '[20~',
        "F10": '\x1b' + '[21~',
        "F11": '\x1b' + '[23~',
        "F12": '\x1b' + '[24~',
        "Down": '\x1b' + '[B',
        "Up": '\x1b' + '[A'
    }

    ControlCodes = {
        "Ctrl-A": '\x01',
        "Ctrl-B": '\x02',
        "Ctrl-C": '\x03',
        "Ctrl-D": '\x04',
        "Ctrl-E": '\x05',
        "Ctrl-F": '\x06',
        "Ctrl-G": '\x07',
        "Ctrl-H": '\x08',
        "Ctrl-I": '\x09',
        "Ctrl-J": '\x0A',
        "Ctrl-K": '\x0B',
        "Ctrl-L": '\x0C',
        "Ctrl-M": '\x0D',
        "Ctrl-N": '\x0E',
        "Ctrl-O": '\x0F',
        "Ctrl-P": '\x10',
        "Ctrl-Q": '\x11',
        "Ctrl-R": '\x12',
        "Ctrl-S": '\x13',
        "Ctrl-T": '\x14',
        "Ctrl-U": '\x15',
        "Ctrl-V": '\x16',
        "Ctrl-W": '\x17',
        "Ctrl-X": '\x18',
        "Ctrl-Y": '\x19',
        "Ctrl-Z": '\x1A',
        "Ctrl-[": '\x1B',
        "Ctrl-\\": '\x1C',
        "Ctrl-]": '\x1D',
        "Ctrl-^": '\x1E',
        "Ctrl-_": '\x1F',
    }

NODES_WITH_KERNEL_BOOT_OPTION_SPACING = ['yow-cgcs-wildcat-76']

class BiosMenus:
    Supermicro = {
        "name": "American Megatrends",
        "options": [{'name': 'Setup', 'index': 0, 'key': 'Del'},
                    {'name': 'Boot Menu', 'index': 1, 'key': ['Esc', '!'], 'tag': 'boot menu'},
                    {'name': 'PXE/LAN', 'index': 2, 'key': 'F12'}],
        "wrap_around": False
    }

    American_Megatrends = {
        "name": "American Megatrends",
        "options": [{'name': 'direct boot', 'index': 0, 'key': 'Enter'},
                    {'name': 'setup', 'index': 1, 'key': 'F2'},
                    {'name': 'boot menu', 'index': 2, 'key': 'F6', 'tag': 'boot menu'},
                    {'name': 'network boot', 'index': 3, 'key': 'F12'}],
        "wrap_around": False
    }

    Ironpass = {
        "name": "American Megatrends",
        "options": [{'name': 'direct boot', 'index': 0, 'key': 'Enter'},
                    {'name': 'setup', 'index': 1, 'key': 'F2'},
                    {'name': 'Boot Menu', 'index': 2, 'key': 'F6', 'tag': 'boot menu'},
                    {'name': 'network boot', 'index': 3, 'key': 'F12'}],
        "wrap_around": False
    }

    HP = {
        "name": "Hewlett-Packard",
        "options": [{'name': 'continue', 'index': 0, 'key': ['Esc', '1']},
                    {'name': 'Setup', 'index': 1, 'key': ['Esc', '9']},
                    {'name': 'Intelligent Provisioning', 'index': 2, 'key': ['ESC', '0']},
                    {'name': 'Boot Override', 'index': 3, 'key': ['ESC', '!']},
                    {'name': 'Network Boot', 'index': 4, 'key': ['ESC', '@'], 'tag': 'boot menu'}],
        "wrap_around": False
    }

    ml350 = {
        "name": "Hewlett",
        "options": [{'name': 'System Utilities', 'index': 0, 'key': ['ESC', 'O', 'p']},
                    {'name': 'Intelligent Provisioning', 'index': 1, 'key': ['ESC', '0']},
                    {'name': 'One Time Boot', 'index': 2, 'key': ['ESC', '!']},
                    {'name': 'Network Boot', 'index': 3, 'key': ['ESC', '@'], 'tag': 'boot menu'}],
        "wrap_around": False
    }

    PowerEdge = {
        "name": "PowerEdge",
        "options": [{"name": "System Setup", "index": 0, 'key': ['ESC', '2']},
                    {"name": "Lifecycle Controller", "index": 1, "key": ['ESC', '0']},
                    {"name": "Boot Manager", "index": 2, "key": ['ESC', '!']},
                    {"name": "PXE (B|b)oot", "index": 3, "key": ['ESC', '@'], 'tag': 'boot menu'}],
        "wrap_around": False
    }

    Phoenix = {
        "name": "Phoenix",
        "options": [{'name': 'System\x1b\[\d;\d+HSetup', 'index': 0, 'key': 'F2'},
                    {'name': 'Lifecycle\x1b\[\d;\d+HController', 'index': 1, 'key': 'F10'},
                    {'name': 'BIOS\x1b\[\d;\d+HBoot\x1b\[\d;\d+HManager', 'index': 2, 'key': 'F11'},
                    {"name": "PXE\x1b\[\d;\d+HBoot", "index": 0, "key": 'F12', 'tag': 'boot menu'}],
        "wrap_around": False
    }


class BootMenus:

    Boot_Device = {
        "name": "boot device",
        "prompt": r"Please select boot device|Boot(\x1b\[\d+;\d+H)*(\s)*From",
        "wrap_around": True
    }

    class Kickstart:

        PXE_Boot = {
            "name": "PXE Boot Menu",
            "prompt": b"Automatic Anaconda / Kickstart Boot Menu",
            "wrap_around": True
        }

        UEFI_Boot = {
            "name": "UEFI Boot Menu",
            "prompt": b"Automatic Anaconda / Kickstart Boot Menu",
            "wrap_around": False
        }

        Security = {
            "name": "PXE Security Menu",
            "prompt": b"Security Profile Enabled Boot Options",
            "option_identifiers": r"\dm?\)\s[\w]+",
            "wrap_around": True
        }

        Controller_Configuration = {
            "name": "Controller Configuration",
            #"prompt":  r'\x1b.*\sController Configuration\s+\*|(\x1b\[\d+;\d+H.*){5,}(\x1b\[01;00H)+',
            "prompt": r'(\x1b.*\*?.*\sController Configuration\s.*\*?(\x1b\[\d+;\d+H)?)',
            "wrap_around": True
        }

        Console = {
            "name": "Console",
            #"prompt": r"\sSecurity\sProfile\sEnabled\s\(default\ssetting\)",
            "prompt": r'\x1b.*\*?.*\s(Serial)|(Graphical) Console(\s).*\*?',
            "wrap_around": True
        }


    class PXE_ISO:

        Kernel = {
            "name": "kernel options",
            "prompt": b"Boot from hard drive",
            "option_identifiers": b"hard drive|Controller Configuration",
            "wrap_around": True
        }

        Controller_Configuration = {
            "name": "Controller Configuration",
            #"prompt": b"\x1b\[0;1;36;44m\s+(\w|-)+ (\(?low(\s|_)?latency\)? )?Controller Configuration",
            "prompt": r'(\x1b.*\*?.*\sController Configuration\s.*\*?(\x1b\[\d+;\d+H)?)|Use the . and . keys to'
                      r' change the selection',
            "option_identifiers": "Serial|Graphical",
            "wrap_around": True
        }

        # Serial_Console = {
        #     "name": "Console",
        #     "prompt": r'(\x1b.*\*?.*\s(Serial)|(Graphical) Console(\s).*\*?)|Use the \^ and v keys to '
        #               r'change the selection',
        #     "option_identifiers": "STANDARD|EXTENDED",
        #     "wrap_around": True
        # }


    class USB:

        Kernel = {
            "name": "kernel options",
            "prompt": b"Select kernel options and boot kernel",
            "option_identifiers": b"Controller Configuration",
            "wrap_around": True
        }

        Controller_Configuration = {
            "name": "Controller Configuration",
            #"prompt": b"\x1b\[0;1;36;44m\s+(\w|-)+ (\(?low(\s|_)?latency\)? )?Controller Configuration",
            "prompt": r'(\x1b.*\*?.*\sController Configuration\s.*\*?(\x1b\[\d+;\d+H)?)|Use the . and . keys to'
                      r' change the selection',
            "option_identifiers": "Serial|Graphical",
            "wrap_around": True
        }

        # # Serial_Console = {
        # #     "name": "Console",
        # #     "prompt": r'(\x1b.*\*?.*\s(Serial)|(Graphical) Console(\s).*\*?)|Use the \^ and v keys to '
        # #               r'change the selection',
        # #     "option_identifiers": "STANDARD|EXTENDED",
        # #     "wrap_around": True
        # }

    class Sub_Menu_Prompts:

        Controller_Configuration = {
            "wolfpass": r'Use the . and . keys to change the selection',
            "wildcat": r'(\x1b.*\*?.*\sController Configuration\s.*\*?(\x1b\[\d+;\d+H)?)|Use the . and . keys to change the selection',
        }

        Console = {
            "wolfpass": r'Use the . and . keys to change the selection',
            "wildcat": r'(\x1b.*\*?.*\s(Serial)|(Graphical) Console(\s).*\*?)|'
                       r'Use the \^ and v keys to change the selection',
        }




