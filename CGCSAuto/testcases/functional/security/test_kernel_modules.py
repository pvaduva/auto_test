import re
from pytest import mark

from keywords import system_helper, host_helper
from utils.tis_log import LOG


@mark.nightly
def test_kernel_module_signatures():
    """
    Test kernel modules are properly signed on all tis hosts.

    Steps on each host:
        - 'cat /proc/sys/kernel/tainted', ensure value is 4096. If not, do following steps:
            - 'grep --color=never -i "module verification failed" /var/log/kern.log' to find out failed modules
            - 'modinfo <failed_module> | grep --color=never -E "sig|filename" to display signing info for each module

    """
    hosts = system_helper.get_hostnames()
    failed_hosts = {}

    for host in hosts:
        with host_helper.ssh_to_host(host) as host_ssh:
            LOG.tc_step("Check kernel modules on {}".format(host))
            output = host_ssh.exec_cmd('cat /proc/sys/kernel/tainted', fail_ok=False)[1]
            if output != '4096':
                LOG.error("Kernel module verification(s) failed on {}. Collecting more info".format(host))

                LOG.tc_step("Check kern.log for modules with failed verification")
                failed_modules = []
                err_out = host_ssh.exec_cmd('grep --color=never -i "module verification failed" /var/log/kern.log')[1]
                for line in err_out.splitlines():
                    module = (re.findall('\] (.*): module verification failed', line)[0]).strip()
                    if module not in failed_modules:
                        failed_modules.append(module)

                failed_hosts[host] = failed_modules
                LOG.tc_step("Display signing info for {} failed kernel modules: {}".format(host, failed_modules))
                for module in failed_modules:
                    host_ssh.exec_cmd('modinfo {} | grep --color=never -E "sig|filename"'.format(module))

    assert not failed_hosts, "Kernel module signature verification failed on: {}".format(failed_hosts)
