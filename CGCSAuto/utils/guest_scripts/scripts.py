from consts.proj_vars import ProjVar

class TisInitServiceScript(object):
    script_path = "/etc/init.d/tis_automation_init.sh"
    configuration_path = "/etc/init.d/tis_automation_init.config"
    service_name = "tis_automation_init.service"
    service_path = "/etc/systemd/system/{}".format(service_name)
    service = """
[Unit]
Description=TiS Automation Initialization
After=NetworkManager.service network.service wrs-guest-setup.service

[Service]
Type=simple
RemainAfterExit=yes
ExecStart=/bin/bash {} start
ExecStop=/bin/bash {} stop

[Install]
WantedBy=multi-user.target
""".format(script_path, script_path)

    @classmethod
    def configure(cls, vm_ssh, **kwargs):
        cfg = "\n".join(["{}={}".format(*kv) for kv in kwargs.items()])
        vm_ssh.exec_sudo_cmd(
            "cat > {} << 'EOT'\n{}\nEOT".format(cls.configuration_path, cfg), fail_ok=False)
        vm_ssh.exec_sudo_cmd(
            "cat > %s << 'EOT'\n%s\nEOT" % (cls.service_path, cls.service),
            fail_ok=False)

    @classmethod
    def enable(cls, vm_ssh):
        vm_ssh.exec_sudo_cmd(
            "systemctl daemon-reload", fail_ok=False)
        vm_ssh.exec_sudo_cmd(
            "systemctl enable %s" % (cls.service_name), fail_ok=False)

    @classmethod
    def start(cls, vm_ssh):
        vm_ssh.exec_sudo_cmd(
            "systemctl daemon-reload", fail_ok=False)
        vm_ssh.exec_sudo_cmd(
            "systemctl start %s" % (cls.service_name), fail_ok=False)

    @classmethod
    def src(cls):
        return "utils/guest_scripts/tis_automation_init.sh"

    @classmethod
    def dst(cls):
        return cls.script_path
