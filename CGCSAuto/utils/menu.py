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
            try:
                self.find_options(telnet_conn)
            except TypeError:
                LOG.error("{} has no options".format(self.name))
                raise
        if index is not None:
            option = self.options[index]
        elif pattern is not None:
            for item in self.options:
                if hasattr(pattern, "search"):
                    if pattern.search(item.name):
                        option = item
                        break
                else:
                    if pattern in item.name:
                        option = item
                        break
        elif tag is not None:
            for item in self.options:
                if item.tag is not None:
                    if tag == item.tag:
                        option = item
                        break
        else:
            LOG.error("Either name of the option, index, or tag must be given in order to select")
        LOG.info("Selecting {} option {}".format(self.name, option.name))
        if option.key == "Enter" or option.key == "Return":
            while self.index != option.index:
                if option.index > self.index:
                    self.move_down(telnet_conn)
                else:
                    self.move_up(telnet_conn)
        option.enter(telnet_conn)
        self.index = 0

    def find_options(self, telnet_conn, end_of_menu, option_identifier, newline=b"\n"):
        telnet_conn.expect([end_of_menu], 60)
        output = telnet_conn.cmd_output.encode()
        options = re.split(newline, output)
        options = [option for option in options if re.search(option_identifier, option)]
        LOG.debug("{} options are: {}".format(self.name, options))
        for i in range(0, len(options)):
            self.options.append(Option(name=options[i].decode(), index=i))

    def get_sub_menu(self, name, strict=True):
        for sub_menu in self.sub_menus:
            if (name == sub_menu.name and strict) or (name in sub_menu.name and not strict):
                return sub_menu
        return None

    def move_down(self, telnet_conn):
        current_index = self.index
        LOG.info("Entering: Down")
        telnet_conn.write(str.encode(bios.TerminalKeys.Keys["Down"]))
        if current_index < (len(self.options) - 1):
            self.index += 1
        elif self.wrap_around:
            self.index = 0
        time.sleep(1)
        return self.index

    def move_up(self, telnet_conn):
        current_index = self.index
        LOG.info("Entering: Up")
        telnet_conn.write(str.encode(bios.TerminalKeys.Keys["Up"]))
        if current_index > 0:
            self.index -= 1
        elif self.wrap_around:
            self.index = len(self.options) - 1
        time.sleep(1)
        return self.index

    def order_options(self):
        self.options.sort(key=lambda option: option.index)

    def get_current_option(self):
        for option in self.options:
            if option.index == self.index:
                return option

    def get_prompt(self):
        return self.prompt

    def get_name(self):
        return self.name


class BiosMenu(Menu):
    menus = bios.BiosMenus
    lab_menu_dict = {
        'wolfpass|wildcat|grizzly': menus.American_Megatrends,
        'hp': menus.HP,
        'ironpass': menus.Ironpass,
        'ml350': menus.ml350,
        'r730|r430': menus.PowerEdge,
        'r720': menus.Phoenix,
        'supermicro': menus.Supermicro,
    }

    def __init__(self, lab_name=None):
        if lab_name is None:
            lab = InstallVars.get_install_var("LAB")
            lab_name = lab["name"]
        lab_name = lab_name.lower()
        LOG.debug("Lab name: {}".format(lab_name))

        for k, v in self.lab_menu_dict.items():
            if re.search(k, lab_name):
                bios_menu_dict = v
                break
        else:
            raise NotImplementedError('{} not handled'.format(lab_name))

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
        highlight_code = "\x1b[0;7;37;40m" if "PXE" in self.name else "\x1b[0m\x1b[37m\x1b[40m"
        if not self.options:
            self.find_options(telnet_conn)
        for i in range(0, len(self.options)):
            if highlight_code in self.options[i].name:
                self.index = self.options[i].index
        return super().get_current_option()

    def find_options(self, telnet_conn, end_of_menu=b"utomatic(ally)?( boot)? in|Press \[Tab\] to edit",
                     option_identifier=b"(\dm?\))|([\w]+)\s+> ", newline=b'(\x1b\[\d+;\d+H)+'):
        super().find_options(telnet_conn, end_of_menu=end_of_menu, option_identifier=option_identifier, newline=newline)
        # TODO: this is a wasteful way to initialize the Options.
        self.options = [KickstartOption(name=option.name, index=option.index, key=option.key) for option in self.options]
        for option in self.options:
            # TODO: would like to make this more general, but it's impossible to determine the prompt
            if "security" in option.name.lower() and ("  >" in option.name.lower() or "options" in option.name.lower()):
                security_menu = KickstartMenu(name="PXE Security Menu", kwargs=bios.BootMenus.Kickstart.Security)
                self.sub_menus.append(security_menu)
        current_option = self.get_current_option(telnet_conn)
        self.index = current_option.index

    def select(self, telnet_conn, index=None, pattern=None, tag=None):
        if isinstance(tag, str):
            tag_dict = {"os": "centos", "security": "standard", "type": None, "console": "serial"}

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


class USBBootMenu(KickstartMenu):
    def __init__(self):
        super().__init__(name="USB boot menu", kwargs=bios.BootMenus.USB.Kernel)
        public_sub_menu_vars = [getattr(bios.BootMenus.USB, var) for var in vars(bios.BootMenus.USB) if not var.startswith('__')]
        sub_menu_dicts = [public_var for public_var in public_sub_menu_vars if isinstance(public_var, dict)
                          and public_var['name'] != "kernel options"]
        for sub_menu_dict in sub_menu_dicts:
            sub_menu = super().__new__(USBBootMenu)
            Menu.__init__(self=sub_menu, name=sub_menu_dict["name"], kwargs=sub_menu_dict)
            self.sub_menus.append(sub_menu)

    def find_options(self, telnet_conn, end_of_menu=b"utomatic(ally)?( boot)? in|Press \[Tab\] to edit",
                     option_identifier=b"[A-Z][A-Za-z]", newline=b'(\x1b\[\d+;\d+H)+'):
        super().find_options(telnet_conn, end_of_menu=end_of_menu, option_identifier=option_identifier, newline=newline)



class BootDeviceMenu(Menu):
    def __init__(self):
        super().__init__(name="boot device menu", kwargs=bios.BootMenus.Boot_Device)

    # TODO: generalize for the base Menu function
    def find_options(self, telnet_conn, end_of_menu=b"\^ and v to move selection|_q{40,}_", option_identifier=b"[A-Z][A-Za-z]",
                             newline=b'(\x1b\[\d+;\d+H)+'):
        telnet_conn.expect([end_of_menu], 60)
        output = str.encode(telnet_conn.cmd_output)
        positioning_codes = re.findall(newline, output)
        current_index = 0
        next_index = 1
        newline_codes = [positioning_codes[current_index]]

        while True:
            try:
                current_line_num = int(re.search(b"(\[)(\d+)", positioning_codes[current_index]).group(2))
                next_line_num = int(re.search(b"(\[)(\d+)", positioning_codes[next_index]).group(2))
                if next_line_num > current_line_num:
                    newline_codes.append(positioning_codes[next_index])
                current_index += 1
                next_index += 1
            except IndexError:
                break
        option_index = 0
        for i in range(0, len(newline_codes) - 1):
            option_name = output[output.find(newline_codes[i]):output.find(newline_codes[i + 1])]
            if re.search(option_identifier, option_name):
                self.options.append(Option(name=option_name.decode(), index=option_index))
                option_index += 1
        LOG.debug("{} options are: {}".format(self.name, [option.name for option in self.options]))


class Option(object):
    def __init__(self, name, index, key=None, tag=None):
        self.name = name
        self.index = index
        option_name = self.name.lower()

        if key is None:
            has_key = re.search("(press|use)\W*(\w+)", option_name, re.IGNORECASE)
            if has_key:
                match = has_key.group(2)
                self.key = match.capitalize() if match.capitalize() in bios.TerminalKeys.Keys.keys() else match
            else:
                self.key = 'Enter'
        else:
            self.key = key

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
        for input_ in key:
            cmd += bios.TerminalKeys.Keys.get(input_.capitalize(), input_)

        if not cmd:
            cmd = '\n'
        LOG.info("Entering {} to select {} option".format(cmd, self.name))

        telnet_conn.write(cmd.encode())


class KickstartOption(Option):
    def __init__(self, name, index=0, key=None, tag=None):
        tag_dict = {"os": "centos", "security": "standard", "type": None, "console": "serial"}
        super().__init__(name, index, key)
        option_name = self.name.lower()

        if tag is None:
            if "wrl" in option_name or "wrlinux" in option_name:
                tag_dict["os"] = "wrl"

            if "all-in-one" in option_name or "cpe" in option_name or "aio" in option_name:
                tag_dict["type"] = "cpe"
            elif "controller" in option_name:
                tag_dict["type"] = "standard"

            if "security" in option_name and "extended" in option_name:
                tag_dict["security"] = "extended"

            if "lowlat" in option_name or "low lat" in option_name or "low_lat" in option_name:
                tag_dict["type"] = "lowlat"

            if "graphic" in option_name:
                tag_dict["console"] = "graphical"

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
        LOG.debug("Kickstart menu option {} tags are: {}".format(self.name, tag_dict))

