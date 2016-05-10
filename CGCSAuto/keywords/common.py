import pexpect
from consts.auth import Tenant


def scp_from_local(source_path, dest_ip, dest_user='wrsroot', dest_password='li69nux', dest_path='/home/wrsroot',
                   timeout=60, is_dir=False):
    dir_option = '-r ' if is_dir else ''
    cmd = 'scp {}{} {}@{}:{}'.format(dir_option, source_path, dest_user, dest_ip, dest_path)

    __scp_base(cmd, remote_password=dest_password, logdir=dest_path, timeout=timeout)


def scp_to_local(source_path, source_ip, dest_path, source_user='wrsroot', source_password='li69nux', is_dir=False,
                 timeout=60):
    dir_option = '-r ' if is_dir else ''
    cmd = 'scp {}{}@{}:{} {}'.format(dir_option, source_user, source_ip, source_path, dest_path)

    __scp_base(cmd, remote_password=source_password, logdir=dest_path, timeout=timeout)


def __scp_base(cmd, remote_password, logdir=None, timeout=60):
    if logdir:
        logfilepath = logdir + '/scp_files.log'
        logfile = open(logfilepath, 'w+')
    else:
        logfile = None

    local_child = pexpect.spawn(command=cmd, encoding='utf-8', logfile=logfile)
    index = local_child.expect([pexpect.EOF, 'assword:', 'yes/no'], timeout=timeout)

    if index == 2:
        local_child.sendline('yes')
        index = local_child.expect(pexpect.EOF, 'assword:')

    if index == 1:
        local_child.sendline(remote_password)
        local_child.expect(pexpect.EOF)

    if logfile:
        logfile.close()


def get_tenant_name(auth_info=None):
    if auth_info is None:
        auth_info = Tenant.get_primary()
    return auth_info['tenant']


class Count:
    __vm_count = 0
    __flavor_count = 0
    __volume_count = 0
    __image_count = 0

    @classmethod
    def get_vm_count(cls):
        cls.__vm_count += 1
        return cls.__vm_count

    @classmethod
    def get_flavor_count(cls):
        cls.__flavor_count += 1
        return cls.__flavor_count

    @classmethod
    def get_image_count(cls):
        cls.__image_count += 1
        return cls.__image_count
