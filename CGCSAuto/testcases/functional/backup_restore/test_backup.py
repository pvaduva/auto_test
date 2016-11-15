import time

from pytest import fixture, skip, mark
from utils.tis_log import LOG
from keywords import network_helper, nova_helper, cinder_helper, host_helper, glance_helper, common, system_helper
from consts import timeout
from testfixtures.recover_hosts import HostsToRecover
from consts.auth import Tenant, SvcCgcsAuto



def create_backup():
    date =time.strftime("%Y%m%d%H%M")
    cmd = 'sudo config_controller --backup titanium_backup_'+date

    #execute backup command

    #scp backup files to testserver
    source_file = 'scp ~/opt/backups/titanium_backup_'+date+'_system.tgz \
                ~/opt/backups/titanium_backup_'+date+'_image.tgz '

    dest_dir = SvcCgcsAuto.HOME+'/backup_restore'
    dest_path = common.scp_from_active_controller(source_path=source_file, dest_path=,
                               src_user='wrsroot', src_password='Li69nux*',
                               timeout=60, is_dir=False)

    #delete backupfiles from ~/opt/backups
    #execute backup volume command
    #check volumes


#backup system and image
#back up volume
def __create_image(img_os, scope):

    LOG.fixture_step("({}) Get or create a glance image with {} guest OS".format(scope, img_os))
    image_path = glance_helper._scp_guest_image(img_os=img_os)

    img_id = glance_helper.get_image_id_from_name(img_os, strict=True)
    if not img_id:
        img_id = glance_helper.create_image(name=img_os, source_image_file=image_path, disk_format='qcow2',
                                            container_format='bare')[1]

    return img_id



def kill_instance_process(instance_num=None, instance_name=None):
    """
    Function for killing instance process

    :user param:  user name for ssh
    :ip_address param:  IP address value
    :passwd param:  password for ssh
    :instance_num param:  instance name id from the table (instance-00000092)
    :location param: instance location, host name
    :instance_name param: Name of created instance

    :example1: network_helpers.kill_instance_process(self, user="root",
                    ip_address=host_ip_value, passwd="root",
                    instance_num='instance-00000092', instance_name='wtl5-0')
    :example2: network_helpers.kill_instance_process(self, user="root",
                    location='compute-0', passwd="root",
                    instance_num='instance-00000092', instance_name='wrl5-0')
    """
    search_value = "qemu.*" + instance_num
    LOG.info("Search parameter: %s" % search_value)
    kill_cmd = "kill -9 $(ps ax | grep %s | grep -v grep | awk '{print $1}')" % search_value

    # Get the compute
    vm_host = nova_helper.get_vm_host(instance_name)
    with host_helper.ssh_to_host(vm_host) as host_ssh:
        exitcode, output = host_ssh.exec_sudo_cmd(kill_cmd, expect_timeout=900)
        LOG.info("Output: %s" % output)

    table_param = 'OS-EXT-STS:task_state'
    task_state = nova_helper.get_vm_nova_show_value(instance_name, field=table_param)

    LOG.info("task_state: %s" % task_state)
