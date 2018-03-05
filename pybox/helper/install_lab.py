#!/usr/bin/python3
import os
import time
import streamexpect
from consts.timeout import HostTimeout
from consts import env
from utils import kpi
from utils.sftp import sftp_get, sftp_send, send_dir, get_dir
from utils import serial
from helper import host_helper
from utils.install_log import LOG


def get_lab_setup_files(stream, remote_host=None, release='R5', remote_path=None, local_path=None,
                        host_type='Standard'):
    """
    Retrieves necessary setup files from the host specified. If local_path is specified the files in that
    directory will be collected else files will be collected from remote_host
    Args:
        stream(stream): Stream to controller-0, required to put files in correct directories.
        remote_host(str): Host to retrieve files from.
        release(str): Release to use, if none R5 will be used
        remote_path(str): Path to place the files, if none default path will be used
        local_path(str): Path to setup files, if none default path to files will be used
        host_type(str): Type of host either 'AIO' or 'Standard'
    """
    serial.send_bytes(stream, "mkdir /home/wrsroot/images")
    if local_path:
        if not local_path.endswith('/') or not local_path.endswith('\\'):
            local_path = local_path + '/'
        get_lab_setup_scripts(remote_host, release, remote_path, local_path)
    else:
        get_lab_setup_scripts(remote_host, release, remote_path, local_path)
        get_licence(remote_host, release, remote_path, local_path, host_type)
        get_guest_img(stream, remote_host, release, remote_path, local_path)


def get_lab_setup_scripts(remote_host=None, release='R5', remote_path=None, local_path=None):
    """
    Retrieves lab setup scripts including tenant and admin resources.
    Args:
        remote_host(str): Host to retrieve files from.
        release(str): Release to use, if none R5 will be used
        remote_path(str): Path to setup files, if none default path to files will be used
        local_path(str): Path on local machine to store files for transfer to vbox
    """
    if local_path is None:
        local_path = env.FILEPATH + '{}/'.format(release)
    file_path = []
    if remote_path is None:
        if release == 'R5':
            file_path = env.Files.R5['setup']
        elif release == 'R4':
            file_path = env.Files.R4['setup']
        elif release == 'R3':
            file_path = env.Files.R3['setup']
        else:
            file_path = env.Files.R2['setup']
    if remote_host is not None:
        for items in file_path:
            file = items.split('/')
            sftp_get(source=items, remote_host=remote_host, destination=local_path+file.pop())
    send_dir(source=local_path)


def get_licence(remote_host=env.BuildServers.CGTS4['ip'], release='R5', remote_path=None,
                local_path=None, host_type='Standard'):
    """
        Retrieves Licence from specified host and sends it to controller-0.
    Args:
        remote_host(str): Host to retrieve files from.
        release(str): Release to use, if none R5 will be used
        remote_path(str): Path to setup files, if none default path to files will be used
        host_type(str): Type of host either 'AIO' or 'Standard'
        local_path(str): Path on local machine to store files for transfer to vbox
    """
    if local_path is None:
        local_path = env.FILEPATH + '{}/'.format(release)
    file_path = []
    if remote_path is None:
        if release == 'R5':
            file_path = env.Licenses.R5[host_type]
        elif release == 'R4':
            file_path = env.Licenses.R4[host_type]
        elif release == 'R3':
            file_path = env.Licenses.R3[host_type]
        else:
            file_path = env.Licenses.R2[host_type]
    local_path = local_path + 'license.lic'
    sftp_get(source=file_path, remote_host=remote_host, destination=local_path)
    sftp_send(source=local_path, destination='/home/wrsroot/license.lic')


def get_guest_img(stream, remote_host=None, release='R5', remote_path=None,
                  local_path=None):
    """
 Retrieves necessary setup files from the host specified.
    Args:
        stream(stream): Stream to controller-0, required to put files in correct directories.
        remote_host(str): Host to retrieve files from.
        release(str): Release to use, if none R5 will be used
        remote_path(str): Path to setup files, if none default path to files will be used
        local_path(str): Path on local machine to store files for transfer to vbox
    """
    if local_path is None:
        local_path = env.FILEPATH + '{}/'.format(release)
    file_path = []
    if remote_path is None:
        if release == 'R5':
            file_path = env.Builds.R5['guest']
        elif release == 'R4':
            file_path = env.Builds.R4['guest']
        elif release == 'R3':
            file_path = env.Builds.R3['guest']
        else:
            file_path = env.Builds.R2['guest']
    serial.send_bytes(stream, "mkdir /home/wrsroot/images")
    if release != 'R2':
        local_path = local_path + 'tis-centos-guest.img'
    else:
        local_path = local_path + 'cgcs-guest.img'
    if remote_host is not None:
        sftp_get(source=file_path, remote_host=remote_host, destination=local_path)
    if release != 'R2':
        sftp_send(source=local_path, destination="/home/wrsroot/images/tis_centos_guest.img")
    else:
        sftp_send(source=local_path, destination="/home/wrsroot/images/cgcs-guest.img")


def get_patches(cont0_stream, local_path=None, remote_host=None, release='R5'):
    """
    Retrieves patches from remote_host or localhost if remote_host is None
    """
    serial.send_bytes(cont0_stream, "mkdir /home/wrsroot/patches")
    if local_path is None:
        local_path = env.FILEPATH + '{}/patches/'.format(release)
    remote_path = '/home/wrsroot/patches/'
    if remote_host is not None:
        if release == 'R5':
            #patch_loc = env.Builds.R5['patches']
            pass
        elif release == 'R4':
            patch_loc = env.Builds.R4['patches']
        elif release == 'R3':
            patch_loc = env.Builds.R3['patches']
        else:
            patch_loc = env.Builds.R2['patches']
        for items in patch_loc:
            get_dir(items, remote_host, local_path, patch=True)
        send_dir(local_path, destination=remote_path)
    else:
        LOG.info("Retrieving patches from {}".format(local_path))
        if not local_path.endswith('/') or not local_path.endswith('\\'):
            local_path = local_path + '/'
        send_dir(local_path, '10.10.10.3', remote_path)


def get_config_file(remote_host=None, release='R5'):
    """
    Retrieves config file from remote host if specified or localhost if None.
    Sends file to cont0    
    """
    if release == 'R5':
        local_path = env.FILEPATH + '{}/TiS_config.ini_centos'.format(release)
    elif release == 'R2':
        local_path = env.FILEPATH + '{}/system_config'.format(release)
    else:
        local_path = env.FILEPATH + '{}/system_config.centos'.format(release)
    remote_path = '/home/wrsroot/TiS_config.ini_centos'

    if remote_host is not None:
        if release == 'R5':
            sftp_get(env.Files.R5['config'], remote_host, local_path)
        elif release == 'R4':
            sftp_get(env.Files.R4['config'], remote_host, local_path)
        elif release == 'R3':
            sftp_get(env.Files.R3['config'], remote_host, local_path)
        else:
            sftp_get(env.Files.R2['config'], remote_host, local_path)
    sftp_send(local_path, '10.10.10.3', remote_path)


def install_controller_0(stream):
    """
    Runs initial install of  R5 controller-0

    Args:
        stream: Stream to controller-0
    Steps:
        - Checks if controller-0 is locked
        - Checks for lab_setup files
        - Runs first lab_setup iteration
        - Unlocks controller-0
    """
    time.sleep(10)
    serial.send_bytes(stream, "system host-list", expect_prompt=False)

    try:  
        serial.expect_bytes(stream, "locked")
    except streamexpect.ExpectTimeout:
        LOG.info("Controller should be locked when configuration is completed.")
        return 1
    ret = serial.send_bytes(stream, 'ls /home/wrsroot/', prompt="lab_setup.sh", fail_ok=True, timeout=10)
    if ret != 0:
        LOG.info("Lab_setup.sh not found. Please transfer the "
                 "required files before continuing. Press enter once files are obtained.")
        input()
    ret = serial.send_bytes(stream, 'ls /home/wrsroot/images/', prompt="tis-centos-guest.img", fail_ok=True, timeout=10)
    if ret != 0:
        LOG.info("Guest image not found. Please transfer the "
                 "required files before continuing. Press enter once files are obtained.")
        input()
    serial.send_bytes(stream, "sh lab_setup.sh", timeout=HostTimeout.LAB_INSTALL, expect_prompt=False)
    host_helper.check_password(stream)
    ret = serial.expect_bytes(stream, "topping after", timeout=1200, fail_ok=True)
    if ret != 0:
        LOG.info("Lab_setup.sh failed. Pausing to allow for debugging. "
                 "Please re-run the iteration before continuing. Press enter to continue.")
        input()
    start = time.time()
    host_helper.unlock_host(stream, 'controller-0')
    ret = serial.expect_bytes(stream, 'login:', timeout=HostTimeout.CONTROLLER_UNLOCK)
    if ret != 0:
        LOG.info("Controller-0 not unlocked,Pausing to allow for debugging. "
                 "Please re-run the iteration before continuing. Press enter to continue.")
        input()
    host_helper.login(stream)
    end = (time.time() - start)/60
    LOG.info("Controller-0 unlock time: {} minutes".format(end))
    LOG.info("Waiting for services to activate.")
    time.sleep(60)


def run_install_scripts(stream, host_list, aio=False, storage=False, release='R5', streams=None):
    """
    Runs lab install.sh iterations. Currently does not support Simplex systems
    Args:
        stream: Stream to controller-0
        host_list: list of hosts, used when running aio scripts to install controller-1 at the appropriate time
        release: Release that is installed.
        aio: Option to run the script for aio setup
        storage: Option to run the script for storage setup
        streams: Dictionary of streams to nodes
    Steps:
        - Checks for lab_setup files
        - Runs lab_setup iterations
        - Unlocks nodes
    """
    if 'controller-0' in host_list:
        host_list.remove('controller-0')
    serial.send_bytes(stream, "chmod +x *.sh", timeout=20)
    LOG.info("Starting lab install.")
    ret = serial.send_bytes(stream, 'ls /home/wrsroot/', prompt="lab_setup.sh", fail_ok=True, timeout=10)
    if ret != 0:
        LOG.info("Lab_setup.sh not found. Please transfer the "
                 "required files before continuing. Press enter once files are obtained.")
        input()
    if release == 'R5' or release == 'R4':
        ret = serial.send_bytes(stream, 'ls /home/wrsroot/images/', prompt="tis-centos-guest.img", fail_ok=True,
                                timeout=10)
    else:
        ret = serial.send_bytes(stream, 'ls /home/wrsroot/images/', prompt="cgcs-guest.img", fail_ok=True,
                                timeout=10)
    if ret != 0:
        LOG.info("Guest image not found. Please transfer the file before continuing. "
                 "Press enter once guest image is obtained.")
        input()
    start = time.time()
    if aio:
        serial.send_bytes(stream, "source /etc/nova/openrc", prompt='keystone')
        if release != 'R5':
            serial.send_bytes(stream, "./lab_setup.sh", expect_prompt=False, fail_ok=True)
            host_helper.check_password(stream)
            ret = serial.expect_bytes(stream, "topping after", timeout=HostTimeout.LAB_INSTALL, fail_ok=True)
            if ret != 0:
                LOG.info("Lab_setup.sh failed. Pausing to allow for debugging. "
                         "Please re-run the iteration before continuing. Press enter to continue.")
                input()
            LOG.info("Running system compute-config-complete, "
                     "installation will resume once controller-0 reboots and services are active")
            serial.send_bytes(stream, "source/etc/nova/openrc", prompt='keystone')
            serial.send_bytes(stream, "system compute-config-complete", expect_prompt=False)
            serial.expect_bytes(stream, "login:",  timeout=HostTimeout.REBOOT)
            host_helper.login(stream, timeout=60)
        serial.send_bytes(stream, "./lab_setup.sh", expect_prompt=False)
        host_helper.check_password(stream)
        ret = serial.expect_bytes(stream, "topping after", timeout=HostTimeout.LAB_INSTALL, fail_ok=True)
        if ret != 0:
            LOG.info("Lab_setup.sh failed. Pausing to allow for debugging. "
                     "Please re-run the iteration before continuing. Press enter to continue.")
            input()
        if 'controller-1' in host_list:
            LOG.info("Installing controller-1")
            cont1_stream = streamexpect.wrap(serial.connect('controller-1', 10001), echo=True, close_stream=False)
            host_helper.install_host(stream, 'controller-1', 'controller', 2)
            serial.expect_bytes(cont1_stream, "ogin:", timeout=HostTimeout.INSTALL)
            serial.send_bytes(stream, "./lab_setup.sh", expect_prompt=False)
            host_helper.check_password(stream)
            ret = serial.expect_bytes(stream, "topping after", timeout=HostTimeout.LAB_INSTALL, fail_ok=True)
            if ret != 0:
                LOG.info("Lab_setup.sh failed. Pausing to allow for debugging."
                         " Please re-run the iteration before continuing. Press enter to continue.")
                input()
            LOG.info("Unlocking Controller-1")
            host_helper.unlock_host(stream, 'controller-1')
            ret = serial.expect_bytes(cont1_stream, "ogin:")
            if ret == 1:
                LOG.info("Controller-1 not unlocked, pausing to allow for debugging. "
                         "Please unlock before continuing. Press enter to continue.")
                input()
        LOG.info("Completed install successfully.")
    else:
        serial.send_bytes(stream, "source /etc/nova/openrc", prompt='keystone')
        if release != 'R5':
            serial.send_bytes(stream, "./lab_setup.sh", expect_prompt=False)
            host_helper.check_password(stream)
            ret = serial.expect_bytes(stream, "topping after", timeout=HostTimeout.LAB_INSTALL, fail_ok=True)
            if ret != 0:
                LOG.info("Lab_setup.sh failed. Pausing to allow for debugging. "
                         "Please re-run the iteration before continuing. Press enter to continue.")
                input()
        if storage:
            port = 10002
            now = time.time()
            for hosts in host_list:
                if hosts.startswith('storage'):
                    LOG.info("Unlocking {}".format(hosts))
                    host_helper.unlock_host(stream, hosts)
                    for host in host_list:
                        if 'storage' in host and streams == {}:
                            streams[host] = streamexpect.wrap(serial.connect('{}'.format(host), port), echo=True,
                                                              close_stream=False)
                            port += 1
                    for host in host_list:
                        if 'storage' in host:
                            serial.expect_bytes(streams[host], 'ogin:', timeout=HostTimeout.COMPUTE_UNLOCK)
                            LOG.info("Unlock time: {}".format(time.time() - now))
                            host_list.remove(host)
            serial.send_bytes(stream, "./lab_setup.sh", timeout=HostTimeout.LAB_INSTALL, prompt='topping after')
            host_helper.check_password(stream)
            LOG.info("Competed storage node unlock")
        LOG.info("Re-running lab_setup.sh")
        serial.send_bytes(stream, "./lab_setup.sh", expect_prompt=False)
        host_helper.check_password(stream)
        ret = serial.expect_bytes(stream, "topping after", timeout=HostTimeout.LAB_INSTALL, fail_ok=True)
        if ret != 0:
            LOG.info("Lab_setup.sh failed. Pausing to allow for debugging. "
                     "Please re-run the iteration before continuing. Press enter to continue.")
            input()
        for host in host_list:
            ret = host_helper.unlock_host(stream, host)
            if ret == 1:
                LOG.info("{} not unlocked, pausing to allow for debugging. "
                         "Please unlock before continuing. Press enter to continue.".format(host))
                input()
                time.sleep(20)
        LOG.info("Waiting for computes to unlock.")
        now = time.time()

        port = 10001
        for host in host_list:
            if streams[host] is None:
                streams[host] = streamexpect.wrap(serial.connect(host, port), echo=True, close_stream=False)
                port += 1
            time.sleep(120)
        for host in host_list:
            serial.send_bytes(streams[host], '\n', expect_prompt=False)
            # TODO Fix issue with finding 'ogin:' immediately after unlock
            ret = serial.expect_bytes(streams[host], "{} login:".format(host), timeout=HostTimeout.CONTROLLER_UNLOCK, fail_ok=True)
            if ret != 0:
                LOG.info("{} not unlocked, pausing to allow for debugging. "
                         "Please unlock {} before continuing. Press enter to continue.".format(host, host))
                input()
            else:
                LOG.info("Unlock time: {}".format((time.time() - now)/60))
        serial.send_bytes(stream, "./lab_setup.sh", expect_prompt=False)
        host_helper.check_password(stream)
        ret = serial.expect_bytes(stream, "Done", timeout=HostTimeout.LAB_INSTALL, fail_ok=True)
        if ret != 0:
            LOG.info("Lab_setup.sh failed. Pausing to allow for debugging. "
                     "Please re-run the iteration before continuing."
                     " Press enter to continue.")
            input()
        LOG.info("Completed lab install.")
        kpi.LABTIME = time.time()-start
        LOG.info("Lab install time: {}".format(kpi.LABTIME/60))


def config_controller(stream, default=True, release='R5', config_file=None, backup=None, clone_iso=None,
                      restore_system=None, restore_images=None, remote_host=None):
    """
    Configure controller-0 using optional arguments
    Args:
        stream(stream): stream to controller-0
        default(bool): Use default settings
        config_file(str): Config file to use.
        backup(str):
        clone_iso(str):
        release(str): Release version
        restore_system(str):
        restore_images(str):
        remote_host(str): Host to retrieve licence from if necessary
    Steps:
        - Checks for license file
        - Runs config_controller with default argument or with config-file if requested
    """
    # TODO:Currently only uses config_file and default as optional arguments
    args = ''
    if config_file:
        args += '--config-file ' + config_file
    if release != 'R5':
        ret = serial.send_bytes(stream, "ls", prompt='license.lic', fail_ok=True, timeout=10)
        if ret != 0:
            LOG.info("License file not found. Please retrieve license and press enter to continue.")
            input()
    if (release == 'R4' or release == 'R3') and not config_file:
        LOG.info("Configuration fails for R4/3 when using --default. "
                 "Please configure manually before continuing the installation")
        return 1
    LOG.info("Configuring controller-0")
    start = time.time()
    serial.send_bytes(stream, "sudo config_controller {}".format(args), expect_prompt=False)
    host_helper.check_password(stream)
    ret = serial.expect_bytes(stream, "Configuration was applied", timeout=HostTimeout.LAB_CONFIG)
    if ret != 0:
        LOG.info("Configuration failed. Exiting installer.")
        exit()
    kpi.CONFIGTIME = time.time() - start
    LOG.info("Configuration time: {} minutes".format(kpi.CONFIGTIME/60))


def install_patches_before_config(stream, release='R5'):
    """
    Installs patches before controller_config has been run.
    Args:
        stream(stream): Stream to controller-0
        release(str): Release that is being installed.
    Steps:
        - Checks for patches
        - Uploads patch directory
        - Applies patches
        - Installs patches on controller-0
        - Reboots controller-0
    """
    if release == 'R5':
        LOG.info("Currently no patches for R5")
        return
    LOG.info("Installing patches on controller-0")
    ret = serial.send_bytes(stream, "ls /home/wrsroot/patches/", prompt=".patch", fail_ok=True)
    if ret != 0:
        LOG.info("No patches found. PLease copy patches into /home/wrsroot/patches before continuing. "
                 "Press enter to continue.")
        input()
    serial.send_bytes(stream, 'sudo sw-patch upload-dir /home/wrsroot/patches', expect_prompt=False)
    host_helper.check_password(stream)
    serial.send_bytes(stream, 'sudo sw-patch apply --all', timeout=240)
    host_helper.check_password(stream)
    serial.send_bytes(stream, "sudo sw-patch install-local", expect_prompt=False)
    host_helper.check_password(stream)
    serial.expect_bytes(stream, 'reboot', timeout=HostTimeout.INSTALL_PATCHES)
    LOG.info("Rebooting controller-0")
    now = time.time()
    serial.send_bytes(stream, 'sudo reboot', expect_prompt=False)
    host_helper.check_password(stream)
    serial.expect_bytes(stream, 'login:', HostTimeout.REBOOT)
    kpi.REBOOTTIME = time.time()-now
    LOG.info("Length of reboot {} minutes".format(kpi.REBOOTTIME/60))
    host_helper.login(stream)


def enable_lvm(stream, release):
    """
    Enables LVM backend
    Args:
        stream: stream to controller-0.
        release: Release version installed.
    """
    if release != 'R5':
        LOG.info("Storage backends configured in config_controller for non R5 releases.")
        return
    serial.send_bytes(stream, "NODE=controller-0;DEVICE=/dev/sdb;SIZE=10237;sudo parted -s $DEVICE mktable gpt")
    serial.send_bytes(stream, "system host-disk-list 1 | grep /dev/sdb", prompt="10237")
    serial.send_bytes(stream, "DISK=$(system host-disk-list $NODE | grep $DEVICE | awk '{print $2}')")
    serial.send_bytes(stream, "system host-disk-partition-add $NODE $DISK $SIZE -t lvm_phys_vol")
    serial.send_bytes(stream, "system host-lvg-add $NODE cinder-volumes")
    serial.send_bytes(stream, "while true; do system host-disk-partition-list $NODE --nowrap | grep $DEVICE | "
                              "grep Ready; if [ $? -eq 0 ]; then break; fi; sleep 1; done")
    serial.send_bytes(stream, "PARTITION=$(system host-disk-partition-list $NODE --disk $DISK --nowrap | grep "
                              "part1 | awk '{print $2}')")
    serial.send_bytes(stream, "system host-pv-add $NODE cinder-volumes $PARTITION")
    serial.send_bytes(stream, "system storage-backend-add lvm -s cinder --confirmed")
    serial.send_bytes(stream, "while true; do system storage-backend-list | grep lvm | grep configured; if "
                              "[ $? -eq 0 ]; then break; else sleep 10; fi; done")
