from utils.tis_log import LOG

class BiosTypes:
    American_Megatrends = {
        "name": b"American Megatrends",
        "timeout": 2400,
        "boot_device": b"\\x1b\[\d;\d\d;\d\dm.*\|\s(.*?)\|"

    }

    Hewlett = {
        "name": b"Hewlett",
        "system_utilities": ['ESC+O+p', '\x1b' + 'O' + 'p'],
        "intelligent_provisioning": ['ESC+O+m', '\x1b' + 'O' + 'm'],
        "one_time_boot_menu": ['ESC+!', '\x1b' + '!'],
        "network_boot": ['ESC+@', '\x1b' + '@'],
        "timeout": 2400
    }

    Phoenix = {
        "name": b"Phoenix",
        "timeout": 2400,
        "boot_device": b"\x1B\(B(.*)\x1B\(0x"

    }

    PowerEdge = {
        "name": b"PowerEdge",
        "system_setup": ['F2', '\x1b' + '[14~'],
        "lifecycle_controller": ['F10', '\x1b' + '[22~'],
        "boot_manager": ['F11', '\x1b' + '[23~'],
        "pxe_boot": ['F12', '\x1b' + '[24~'],
        "timeout": 2400
    }


def get_install_key(bios_name):
    if bios_name == b"American Megatrends":
        return ('\x1b' + '[17~')
    elif bios_name == b"Hewlett":
        return BiosTypes.Hewlett["network_boot"]
    elif bios_name == b"Phoenix":
        return ('\x1b' + '[24~')
    elif bios_name == b"PowerEdge":
        return BiosTypes.PowerEdge["pxe_boot"]
    else:
        return None



def get_bios_type(lab):
    if 'bios_type' in lab.keys():
        bios_types = [getattr(BiosTypes, item) for item in dir(BiosTypes) if not item.startswith('__')]
        for bios in bios_types:
            if lab['bios_type'] in bios["name"]:
                return bios
        return None
    else:
        if 'ironpass' in lab["name"] or 'supermicro' in lab["name"] or "wildcat" in lab["name"]:
            return BiosTypes.American_Megatrends
        elif 'r730' or 'r430' in lab["name"]:
            LOG.info(lab["name"])
            return BiosTypes.PowerEdge
        elif 'ml350' in lab["name"] or 'hp' in lab["name"]:
            return BiosTypes.Hewlett
        elif "r720" in lab["name"]:
            return BiosTypes.Phoenix
        else:
            return None

