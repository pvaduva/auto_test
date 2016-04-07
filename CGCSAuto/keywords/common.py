from utils.tis_log import LOG
from consts.auth import Primary


def collect_tis_logs(con_ssh=None):
    # TODO: lock hosts if hosts are unlocked and not online
    LOG.info("Collecting all logs upon test case fail.")
    con_ssh.send('collect all')
    expect_list = ['.*\(yes/no\)\?', '.*password:', 'Compressing Tarball ..: /scratch/ALL_NODES_.*', con_ssh.prompt]
    expect_rtn = -1
    while not expect_rtn == 2:
        expect_rtn = con_ssh.expect(expect_list, timeout=60)
        if expect_rtn == 0:
            con_ssh.send('yes')
        elif expect_rtn == 1:
            con_ssh.send(con_ssh.password)
        elif expect_rtn == 3:
            LOG.error("Collecting logs failed. No ALL_NODES logs found.")
            return


def get_tenant_name(auth_info=None):
    if auth_info is None:
        auth_info = Primary.get_primary()
    return auth_info['tenant']


class Count:
    __vm_count = 0
    __flavor_count = 0
    __volume_count = 0

    @classmethod
    def get_vm_count(cls):
        cls.__vm_count += 1
        return cls.__vm_count

    @classmethod
    def get_flavor_count(cls):
        cls.__flavor_count += 1
        return cls.__flavor_count
