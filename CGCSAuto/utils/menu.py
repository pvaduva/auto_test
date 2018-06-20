import time
import re
from utils.tis_log import LOG
from consts.proj_vars import InstallVars, ProjVar
from consts import bios
from consts.cgcs import SysType


class Menu(object):
    def __init__(self, name, options=None, index=0, prompt=None, wrap_around=True, sub_menus=None, kwargs=None):
        if kwargs:
            options = []
            sub_menus = []
            self.name = kwargs["name"]
            self.index = kwargs.get("index", index)
            self.prompt = kwargs.get("prompt", kwargs["name"])
            self.wrap_around = kwargs.get("wrap_around", True)
            if kwargs.get("options"):
                option_count = 0
                for option in kwargs["options"]:
                    option_name = option.get("name")
                    option_index = option.get("index", option_count)
                    option_key = option.get("key")
                    option_tag = option.get("tag")
                    options.append(Option(name=option_name, index=option_index, key=option_key, tag=option_tag))
                    option_count += 1
            self.options = options
            self.sub_menus = [] if sub_menus is None else sub_menus
        else:
            self.name = name
            self.options = [] if options is None else options
            self.index = index
            self.prompt = self.name if prompt is None else prompt
            self.wrap_around = wrap_around
            self.sub_menus = [] if sub_menus is None else sub_menus

    def select(self, telnet_conn, index=None, pattern=None, tag=None):
        if not self.options:
            self.find_options(telnet_conn)
        if index is not None:
            option = self.options[index]
        elif pattern is not None:
            for item in self.options:
                if hasattr(pattern, "search"):
                    if pattern.search(item.name):
                        option = item
                        index = option.index
                        break
                else:
                    if pattern in item.name:
                        option = item
                        index = option.index
                        break
        elif tag is not None:
            for item in self.options:
                if item.tag is not None:
                    if tag == item.tag:
                        option = item
                        index = item.index
                        break
        else:
            LOG.error("Either name of the option, index, or tag must be given in order to select")
        LOG.info("Selecting {} option {}".format(self.name, option.name))
        key = option.key
        if key == "Enter" or key == "Return" and index > 0:
            while self.index != index:
                if index > self.index:
                    self.move_down(telnet_conn)
                else:
                    self.move_up(telnet_conn)
        self.enter_key(telnet_conn, key)

    def find_options(self, telnet_conn, end_of_menu, option_identifier, newline=b"\n"):
        telnet_conn.expect([end_of_menu], 60)
        output = str.encode(telnet_conn.cmd_output)
        options = re.split(newline, output)
        # TODO: use list comprehension to make this more readable
        options = list(filter(lambda option_string: re.search(option_identifier, option_string), options))
        LOG.debug("{} options are: {}".format(self.name, options))
        for i in range(0, len(options)):
            option = Option(name=options[i].decode(), index=i, key="Enter")
            self.options.append(option)

    def get_sub_menu(self, name, strict=True):
        for sub_menu in self.sub_menus:
            if (name == sub_menu.name and strict) or (name in sub_menu.name and not strict):
                return sub_menu
        return None

    def move_down(self, telnet_conn):
        current_index = self.index
        self.enter_key(telnet_conn, "Down")
        if current_index < (len(self.options) - 1):
            self.index += 1
        elif self.wrap_around:
            self.index = 0
        return self.index

    def move_up(self, telnet_conn):
        current_index = self.index
        self.enter_key(telnet_conn, "Up")
        if current_index > 0:
            self.index -= 1
        elif self.wrap_around:
            self.index = len(self.options) - 1
        return self.index

    @staticmethod
    def enter_key(telnet_conn, key="Enter"):
        if isinstance(key, str):
            key = [key]
        cmd = ''
        for input in key:
            cmd += bios.TerminalKeys.Keys.get(input.capitalize(), input)
        LOG.info("Entering: {}".format(" + ".join(key)))
        telnet_conn.write(str.encode(cmd))
        time.sleep(1)

    def get_current_option(self):
        return self.options[self.index]

    def get_prompt(self):
        return self.prompt

    def get_name(self):
        return self.name


class BiosMenu(Menu):
    def __init__(self, lab_name=None):
        if lab_name is None:
            lab = InstallVars.get_install_var("LAB")
            lab_name = lab["name"]
        lab_name = lab_name.lower()
        LOG.debug("Lab name: {}".format(lab_name))
        if 'wolfpass' in lab_name or "wildcat" in lab_name:
            bios_menu_dict = bios.BiosMenus.American_Megatrends
        elif 'supermicro' in lab_name:
            bios_menu_dict = bios.BiosMenus.Supermicro
        elif 'ironpass' in lab_name:
            bios_menu_dict = bios.BiosMenus.Ironpass
        elif 'r730' in lab_name or 'r430' in lab_name:
            bios_menu_dict = bios.BiosMenus.PowerEdge
        elif 'ml350' in lab_name or 'hp' in lab_name:
            bios_menu_dict = bios.BiosMenus.ml350
        elif "r720" in lab_name:
            bios_menu_dict = bios.BiosMenus.Phoenix

        super().__init__(name=bios_menu_dict["name"], kwargs=bios_menu_dict)

    def get_boot_option(self):
        for option in self.options:
            if option.tag == "boot menu":
                return option


class KickstartMenu(Menu):
    def __init__(self, uefi=False, name=None, options=None, index=0, prompt=None, wrap_around=True, sub_menus=None,
                 kwargs=None):
        if name is None:
            name = "UEFI boot menu" if uefi else "PXE boot menu"
        if prompt is None and kwargs is None:
            kwargs = bios.BootMenus.Kickstart.UEFI_Boot if uefi else bios.BootMenus.Kickstart.PXE_Boot
        super().__init__(name=name, options=options, index=index, prompt=prompt, wrap_around=wrap_around, sub_menus=sub_menus,
                         kwargs=kwargs)

    def get_current_option(self, telnet_conn):
        if not self.options:
            highlight_code = "[0;7;37;40m" if "PXE" in self.name else "^[[0m^[[30m^[[47m^"
            self.find_options(telnet_conn)
            for i in range(0, len(self.options)):
                if highlight_code in self.options[i].name:
                    self.index = self.options[i].index
                    return self.options[i]
            return self.options[0]
        else:
            super().get_current_option()

    def find_options(self, telnet_conn):
        super().find_options(telnet_conn, end_of_menu=b"utomatic(ally)?( boot)? in|Press \[Tab] to edit",
                             option_identifier=b"(\dm?\))|([\w]+)\s+> ", newline=b'(\x1b\[\d+;\d+H)+')
        # TODO: this is a wasteful way to initialize the Options.
        self.options = [KickstartOption(name=option.name, index=option.index, key=option.key) for option in self.options]
        for option in self.options:
            # TODO: would like to make this more general, but it's impossible to determine the prompt
            if "security" in option.name.lower() and "  >" in option.name.lower():
                security_menu = KickstartMenu(name="PXE Security Menu", kwargs=bios.BootMenus.Kickstart.Security)
                self.sub_menus.append(security_menu)

    def select(self, telnet_conn, index=None, pattern=None, tag=None):
        if isinstance(tag, str):
            tag_dict = {"os": "centos", "security": "standard", "type": None}

            if "security" in tag or "extended" in tag:
                tag_dict["security"] = "extended"
                if InstallVars.get_install_var("LOW_LATENCY"):
                    tag_dict["type"] = "lowlatency"
                else:
                    install_type = ProjVar.get_var("SYS_TYPE")
                    if install_type == SysType.AIO_SX or install_type == SysType.AIO_DX:
                        tag_dict["type"] = "cpe"
                    elif install_type == SysType.REGULAR or install_type == SysType.STORAGE:
                        tag_dict["type"] = "standard"
            else:
                tag_dict["type"] = tag
            tag = tag_dict

        super().select(telnet_conn, index, pattern, tag)


class USBBootMenu(Menu):
    def __init__(self):
        super().__init__(name="USB boot menu", kwargs=bios.BootMenus.USB.Kernel)
        # TODO: use list comprehension to make this more readable
        menu_dicts = filter(lambda is_sub_menu: isinstance(is_sub_menu, dict) and is_sub_menu['name'] != "kernel options",
                            [getattr(bios.BootMenus.USB, item) for item in dir(bios.BootMenus.USB)])
        for menu_dict in menu_dicts:
            sub_menu = super().__new__(USBBootMenu)
            Menu.__init__(self=sub_menu, name=menu_dict["name"], kwargs=menu_dict)
            self.sub_menus.append(sub_menu)

    def find_options(self, telnet_conn):
        super().find_options(telnet_conn, end_of_menu=b"Press \[Tab] to edit",
                             option_identifier=b"[A-Z][A-Za-z]", newline=b'(\x1b\[\d+;\d+H)+')


class BootDeviceMenu(Menu):
    def __init__(self):
        super().__init__(name="boot device menu", kwargs=bios.BootMenus.Boot_Device)

    def find_options(self, telnet_conn):
        super().find_options(telnet_conn, end_of_menu=b"\^ and v to move selection|_q{40,}_", option_identifier=b"[A-Z][A-Za-z]",
                             newline=b'(\x1b\[\d+;\d+H)+')


class Option(object):
    def __init__(self, name, index=0, key=None, tag=None):
        self.name = name
        self.index = index
        option_name = self.name.lower()

        if key is None:
            if "press" in option_name or "use" in option_name:
                for key in bios.TerminalKeys.Keys.keys():
                    if key.lower() in option_name:
                        self.key = key
                        break
            else:
                self.key = 'Enter'
        else:
            self.key=key

        if tag is None:
            # bios options
            if "boot menu" in option_name or "network boot" in option_name or "pxe boot" in option_name:
                tag = "boot menu"
            elif "setup" in option_name:
                tag = "setup"

        self.tag = tag
        LOG.debug("{} option tag is {}".format(self.name, self.tag if self.tag else "None"))

    def enter(self, telnet_conn):
        key = [self.key] if isinstance(self.key, str) else self.key
        cmd = ''
        for input in key:
            cmd += bios.TerminalKeys.Keys.get(input.capitalize(), input)
        LOG.info("Entering: {}".format(" + ".join(key)))
        telnet_conn.write(str.encode(cmd))

class KickstartOption(Option):
    def __init__(self, name, index=0, key=None, tag=None):
        tag_dict = {"os": None, "security": "standard", "type": None}
        super().__init__(name, index, key)
        option_name = self.name.lower()

        if tag is None:
            if "wrl" in option_name or "wrlinux" in option_name:
                tag_dict["os"] = "wrl"
            else:
                tag_dict["os"] = "centos"

            if "all-in-one" in option_name or "cpe" in option_name or "aio" in option_name:
                tag_dict["type"] = "cpe"
            elif "controller" in option_name:
                tag_dict["type"] = "standard"

            if "security" in option_name:
                if "standard" in option_name:
                    tag_dict["security"] = "standard"
                else:
                    tag_dict["security"] = "extended"

            if "lowlat" in option_name or "low lat" in option_name or "low_lat" in option_name:
                tag_dict["type"] = "lowlatency"

        elif isinstance(tag, str):
            tag = tag.lower()
            if "all-in-one" in tag or "cpe" in tag or "aio" in tag:
                tag_dict["type"] = "cpe"
            if "standard" in tag:
                tag_dict["type"] = "standard"
            if "lowlat" in tag or "low lat" in tag or "low_lat" in tag:
                tag_dict["type"] = "lowlatency"
            if "security" in tag or "extended" in tag:
                tag_dict["security"] = "extended"

        elif isinstance(tag, dict):
            tag_dict = tag

        self.tag = tag_dict
        LOG.debug("Kickstart menu option {} tags are: ".format(self.name), tag_dict)

