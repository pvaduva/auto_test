class TerminalKeys:
    Keys = {
        "Enter": '\r\r',
        "Return": '\r\r',
        "Esc": '\x1b',
        "Escape": '\x1b',
        "Ctrl": 'placeholder',
        "Control": "placeholder",
        "Insert": "placeholder",
        "Del": "placeholder",
        "Delete": "placeholder",
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
                    {"name": "PXE boot", "index": 3, "key": ['ESC', '@'], 'tag': 'boot menu'}],
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
        "prompt": "Please select boot device|Boot(\x1b\[\d+;\d+H)*(\s)*From",
        "wrap_around": True
    }

    class Kickstart:

        PXE_Boot = {
            "name": "PXE Boot Menu",
            "prompt": "Automatic Anaconda / Kickstart Boot Menu",
            "wrap_around": True
        }

        UEFI_Boot = {
            "name": "UEFI Boot Menu",
            "prompt": "Automatic Anaconda / Kickstart Boot Menu",
            "wrap_around": False
        }

        Security = {
            "name": "PXE Security Menu",
            "prompt": "Security Profile Enabled Boot Options",
            "wrap_around": True
        }

    class USB:

        Kernel = {
            "name": "kernel options",
            "prompt": b"Select kernel options and boot kernel",
            "wrap_around": True
        }

        Controller_Configuration = {
            "name": "Controller Configuration",
            "prompt": b"\x1b\[0;1;36;44m\s+(\w|-)+ (\(?low(\s|_)?latency\)? )?Controller Configuration",
            "index": 0,
            "wrap_around": True
        }

        Serial_Console = {
            "name": "Serial Console",
            "wrap_around": True
        }
