import time
import datetime

from consts.build_server import DEFAULT_BUILD_SERVER
from consts.filepaths import BuildServerPath

from keywords import install_helper


def wait_for_new_host_and_guest_load(build_server=DEFAULT_BUILD_SERVER,
                                     host_build_dir=BuildServerPath.DEFAULT_HOST_BUILD_PATH,
                                     host_trigger_window=4, host_timeout=4,
                                     guest_build_dir=BuildServerPath.DEFAULT_GUEST_IMAGE_PATH,
                                     guest_trigger_window=4, guest_timeout=0.3):

    is_new_build_avail = wait_for_new_host_load(build_server=build_server, build_dir=host_build_dir,
                                                trigger_window=host_trigger_window, timeout=host_timeout)
    if is_new_build_avail:
        wait_for_new_guest_load(build_server=build_server, build_dir=guest_build_dir,
                                trigger_window=guest_trigger_window, timeout=guest_timeout)
    else:
        return False

    return True


def wait_for_new_host_load(build_server=DEFAULT_BUILD_SERVER, build_dir=BuildServerPath.DEFAULT_HOST_BUILD_PATH,
                           trigger_window=4, timeout=4):
    return __wait_for_new_load(build_server, build_dir=build_dir, trigger_window=trigger_window, timeout=timeout)


def wait_for_new_guest_load(build_server=DEFAULT_BUILD_SERVER, build_dir=BuildServerPath.DEFAULT_GUEST_IMAGE_PATH,
                            trigger_window=1, timeout=0.3):
    """
    Wait for new guest load to appear on given build server. This function should be called after
    wait_for_new_host_load() returns True.

    Args:
        build_server (str):
        build_dir ():
        trigger_window (int|float):
        timeout:

    Returns:

    """
    return __wait_for_new_load(build_server, build_dir=build_dir, trigger_window=trigger_window, timeout=timeout)


def __wait_for_new_load(build_server, build_dir, trigger_window, timeout):
    minutes = int(trigger_window * 60)

    with install_helper.ssh_to_build_server(bld_srv=build_server) as bld_srv_ssh:

        window_time = datetime.timedelta(minutes=minutes)
        end_time = time.time() + int(timeout * 3600)
        while time.time() < end_time:
            latest_bld_time = get_modify_time(bld_srv_ssh, build_dir)
            current_time = get_current_time(ssh_client=bld_srv_ssh)
            if current_time < latest_bld_time + window_time:
                # print("New build available from {}:{}".format(build_server, build_dir))
                return True

            time.sleep(60)
        else:
            # print("No new build (modified within {} hours) available from {}:{} after {} hours polling".format(
            #        trigger_window, build_server, build_dir, timeout))
            return False


def get_current_time(ssh_client):
    output = ssh_client.exec_cmd('date', rm_date=False, get_exit_code=False)[1]
    # sample output: Mon Dec 12 08:54:08 EST 2016
    current_time = datetime.datetime.strptime(output, "%a %b %d %H:%M:%S EST %Y")
    return current_time


def get_modify_time(ssh_client, file_path):
    mod_str = "Modify: "
    raw_output = ssh_client.exec_cmd('stat {} | grep --color="never" {}'.format(file_path, mod_str))[1]
    # sample raw_output: Modify: 2016-12-12 00:44:01.783549132 -0500
    time_str = raw_output.split(sep=mod_str)[1].split(sep='.')[0].strip()
    # sample time_str: 2016-12-12 00:44:0
    mod_time = datetime.datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
    return mod_time


def __get_latest_build_dir(build_server, build_dir):
    with install_helper.ssh_to_build_server(bld_srv=build_server) as bld_srv_ssh:
        output = bld_srv_ssh.exec_cmd('ls -l {} | grep --color="never" "latest_build"'.format(build_dir))[1]
        build_dir_ = output.split(sep=r'/')[-1]
        # print("Latest build dir: {}".format(build_dir_))

        return build_dir_


def get_latest_host_build_dir(build_server=DEFAULT_BUILD_SERVER,
                              latest_build_simlink=BuildServerPath.DEFAULT_HOST_BUILD_PATH):
    return __get_latest_build_dir(build_server=build_server, build_dir=latest_build_simlink)
