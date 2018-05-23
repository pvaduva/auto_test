import time
import re
from utils.tis_log import LOG
from consts.proj_vars import InstallVars
from consts import bios


class Menu(object):
    def __init__(self, name, options=None, index=0, prompt=None, wrap_around=True, kwargs=None):
        if kwargs:
            self.name = kwargs["name"]
            self.index = kwargs.get("index", index)
            options = []
            self.prompt = kwargs.get("prompt", kwargs["name"])
            self.wrap_around = kwargs.get("wrap_around", True)
            if kwargs.get("options"):
                for option in kwargs["options"]:
                    options.append(Option(name=option["name"], index=option["index"], key=option["key"]))
            self.options = options
        else:
            self.name = name
            self.options = [] if options is None else options
            self.index = index
            self.prompt = self.name if prompt is None else prompt
            self.wrap_around = wrap_around

    def select(self, telnet_conn, index=None, pattern=None):
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
        else:
            LOG.error("Either name of the option or index must be given in order to select")

        key = option.key
        if key == "Enter" or key == "Return" and index > 0:
            while self.index != index:
                if index > self.index:
                    self.move_down(telnet_conn)
                else:
                    self.move_up(telnet_conn)
        LOG.info("Selecting {} option {}".format(self.name, option.name))
        self.enter_key(telnet_conn, key)

    def find_options(self, telnet_conn, end_of_menu, option_identifier, newline="\n"):
        telnet_conn.expect([end_of_menu], 60)
        output = telnet_conn.cmd_output
        options = output.split(newline)
        options = list(filter(lambda option_string: re.search(option_identifier, str.encode(option_string)), options))
        LOG.debug("{} options are: {}".format(self.name, options))
        for i in range(0, len(options)):
            option = Option(name=options[i], index=i, key="Enter")
            self.options.append(option)

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

        if 'wolfpass' in lab_name or "wildcat" in lab_name:
            bios_menu_dict = bios.BiosMenus.American_Megatrends
        elif 'supermicro' in lab_name:
            bios_menu_dict = bios.BiosMenus.Supermicro
        elif 'ironpass' in lab_name:
            bios_menu_dict = bios.BiosMenus.Ironpass
        elif 'r730' or 'r430' in lab_name:
            bios_menu_dict = bios.BiosMenus.PowerEdge
        elif 'ml350' in lab_name or 'hp' in lab_name:
            bios_menu_dict = bios.BiosMenus.ml350
        elif "r720" in lab_name:
            bios_menu_dict = bios.BiosMenus.Phoenix

        super().__init__(name=bios_menu_dict["name"], kwargs=bios_menu_dict)

    def get_boot_option(self):
        for option in self.options:
            option_name = option.name.lower()
            if "boot menu" in option_name or "network boot" in option_name or "boot manager" in option_name:
                return option


class KickstartMenu(Menu):
    def __init__(self, uefi=False, security="standard"):
        if uefi:
            super().__init__(name="UEFI boot menu", kwargs=bios.BootMenus.UEFI_Boot)
        else:
            super().__init__(name="PXE boot menu", kwargs=bios.BootMenus.PXE_Boot)
        if security.lower() == "extended":
            # TODO: figure out sub_menus
            self.sub_menus = []

    def get_current_option(self, telnet_conn):
        if not self.options:
            highlight_code = "[0;7;37;40m"
            self.find_options(telnet_conn)
            for i in range(0, len(self.options)):
                if highlight_code in self.options[i].name:
                    self.index = self.options[i].index
                    return self.options[i]
        else:
            super().get_current_option()

    def find_options(self, telnet_conn):
        super().find_options(telnet_conn, end_of_menu=b"Press \[Tab] to edit options", option_identifier=b"m\)",
                             newline='\x1b[0;30;44m\x0ex\x0f\x1b')


class USBBootMenu(Menu):
    def __init__(self):
        super().__init__(name="USB boot menu", kwargs=bios.BootMenus.USB.Kernel)
        controller_configuration = Menu(name="Controller Configuration", kwargs=bios.BootMenus.USB.Controller_Configuration)
        serial_console = Menu(name="Serial Console", kwargs=bios.BootMenus.USB.Serial_Console)
        self.sub_menus= [controller_configuration, serial_console]


class BootDeviceMenu(Menu):
    def __init__(self):
        super().__init__(name="boot device menu", kwargs=bios.BootMenus.Boot_Device)

    def find_options(self, telnet_conn):
        super().find_options(telnet_conn, end_of_menu=b"\^ and v to move selection", option_identifier=b"[A-Z][A-Za-z]",
                             newline=';1H')


class Option(object):
    def __init__(self, name, index=0, key=None):
        self.name = name
        self.index = index
        self.key = 'Enter' if key is None else key

    def enter(self, telnet_conn):
        key = [self.key] if isinstance(self.key, str) else self.key
        cmd = ''
        for input in key:
            cmd += bios.TerminalKeys.Keys.get(input.capitalize(), input)
        LOG.info("Entering: {}".format(" + ".join(key)))
        telnet_conn.write(str.encode(cmd))

