# Automated test cases for some of the tests for US82830
#
import re

from pytest import fixture, skip, mark
from consts import timeout
from keywords import host_helper, system_helper
from utils.tis_log import LOG
from utils.ssh import ControllerClient


@fixture(scope='module')
def get_patch_name():
    """
    Assumes that the patch has been stored in /home/wrsroot/test_patches on the server
    - Change patch_name to whatever the patch's name is before testing
    """
    patch_name = 'TS_16.10_FC_TEST_ALLNODES_RR'

    return patch_name


def check_logs(search_for, lines=10, api=False):
    """
    Searches through /var/log/patching.log or /var/log/patching-api.log for the strings given in search_for
    Args:
        lines (int): the number of lines to look through
        api (bool): Whether to search in patching.log or patching-api.log
        search_for (list): list of regular expressions to look for in the logs

    Returns (bool):
        True  - if all the logs were found
        False - otherwise

    """
    cmd = 'tail --lines={} '.format(lines)
    if api:
        cmd += '/var/log/patching-api.log'
    else:
        cmd += '/var/log/patching.log'

    con_ssh = ControllerClient.get_active_controller()
    code, out = con_ssh.exec_cmd(cmd)
    out = out.split('\n')
    found = []

    for i in range(0, len(search_for)):
        LOG.tc_step("Searching for logs containing: {}".format(search_for[i]))
        regex = re.compile(search_for[i])
        for line in out:
            if search_for[i] not in found and re.search(regex, line):
                found.append(search_for[i])
                LOG.info('Found: {}'.format(line))
                break

    return len(search_for) == len(found)


def search_query_table(table_, search_for):
    """
    Searches a table created by sw-patch query or query-hosts for the given values
    Args:
        table_ (list): the output of the commands separated by new lines
        search_for (list): list of values to look for. The first item must be the host's name

    Returns (list):
        subset of the original search_for list of items that were found in the table

    """
    lines = table_
    found = []

    for line in lines:
        parts = re.split(r'\s{2,}', line)
        if parts[0] == search_for[0]:
            LOG.info(parts)
            for i in range(0, len(search_for)):
                LOG.tc_step("Searching for: {}".format(search_for[i]))
                if search_for[i] not in found and search_for[i] in parts:
                    found.append(search_for[i])
                    LOG.info('Found: {}'.format(search_for[i]))

    return found


def check_dir(patch_name):
    con_ssh = ControllerClient.get_active_controller()
    code, out = con_ssh.exec_sudo_cmd('sw-patch query')
    out = out.split('\n')

    search_for = [patch_name, 'Available']
    found = search_query_table(out, search_for)
    return len(search_for) == len(found)


@mark.p3
def test_upload_dir_log(get_patch_name):
    """
    Checks that the correct logs are added when uploading a directory of patches

    Test Steps:
        - Upload patches from a directory
        - Check the log files for the expected logs

    """

    patch_name = get_patch_name
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Uploading patches from directory")
    con_ssh.exec_sudo_cmd('sw-patch upload-dir test_patches')

    res_1 = check_dir(patch_name)

    search_for = ['sw-patch-controller-daemon.*INFO: Importing patches:.*{}'.format(patch_name),
                  'sw-patch-controller-daemon.*INFO: Importing patch:.*{}'.format(patch_name)]
    res_2 = check_logs(search_for, lines=20, api=False)

    search_for = ['sw-patch-controller-daemon.*INFO: User: wrsroot/admin Action: Importing patches:.*{}.patch'
                  .format(patch_name),
                  'sw-patch-controller-daemon.*INFO: User: wrsroot/admin Action: Importing patch:.*{}.patch'
                  .format(patch_name)]
    res_3 = check_logs(search_for, lines=10, api=True)

    LOG.tc_step("Deleting patch {}".format(patch_name))
    con_ssh.exec_sudo_cmd('sw-patch delete {}'.format(patch_name))

    assert res_1, "FAIL: The patch was not in \"sw-patch query\""
    assert res_2, "FAIL: uploading patches did not generate the expected logs in patching.log"
    assert res_3, "FAIL: uploading patches did not generate the expected logs in patching-api.log"


@mark.p3
def test_what_requires_log(get_patch_name):
    """
    Checks that the what_requires query is logged

    Test Steps:
        - Upload a patch and execute 'sw-patch what-requires'
        - Check log files for the expected logs

    """
    patch_name = get_patch_name
    con_ssh = ControllerClient.get_active_controller()
    LOG.tc_step("Uploading patch {}".format(patch_name))
    con_ssh.exec_sudo_cmd('sw-patch upload test_patches/{}.patch'.format(patch_name))
    con_ssh.exec_sudo_cmd('sw-patch what-requires {}'.format(patch_name))

    search_for = ['sw-patch-controller-daemon.*INFO: Querying what requires patches:.*{}'.format(patch_name)]
    res_1 = check_logs(search_for, lines=10, api=False)

    search_for = ['sw-patch-controller-daemon.*INFO: User: wrsroot/admin Action: '
                  'Querying what requires patches:.*{}'.format(patch_name)]
    res_2 = check_logs(search_for, lines=10, api=True)

    LOG.tc_step("Deleting patch {}".format(patch_name))
    con_ssh.exec_sudo_cmd('sw-patch delete {}'.format(patch_name))

    assert res_1, "FAIL: uploading patches did not generate the expected logs in patching.log"
    assert res_2, "FAIL: uploading patches did not generate the expected logs in patching-api.log"


@fixture(scope='function')
def setup_host_install(request, get_patch_name):
    con_ssh = ControllerClient.get_active_controller()
    hosts = host_helper.get_nova_hosts()
    host = hosts[len(hosts) - 1]
    if host == system_helper.get_active_controller_name():
        host = hosts[len(hosts) - 2]
    host_helper.lock_host(host)

    patch_name = get_patch_name
    LOG.fixture_step("Applying {} to patching controller".format(patch_name))
    con_ssh.exec_sudo_cmd('sw-patch upload test_patches/{}.patch'.format(patch_name))
    con_ssh.exec_sudo_cmd('sw-patch apply {}'.format(patch_name))

    def delete_patch():
        LOG.fixture_step("Removing {} from patching controller".format(patch_name))
        con_ssh.exec_sudo_cmd('sw-patch remove {}'.format(patch_name))
        con_ssh.exec_sudo_cmd('sw-patch delete {}'.format(patch_name))
        LOG.fixture_step("Reinstalling {} to revert the patch".format(patch_name))
        con_ssh.exec_sudo_cmd('sw-patch host-install {}'.format(host), expect_timeout=timeout.CLI_TIMEOUT)
        host_helper.unlock_host(host)

    request.addfinalizer(delete_patch)
    return patch_name, host


def check_install(host):
    con_ssh = ControllerClient.get_active_controller()
    code, out = con_ssh.exec_sudo_cmd('sw-patch query-hosts')
    out = out.split('\n')
    search_for = [host, 'Yes']
    found = search_query_table(out, search_for)
    return len(search_for) == len(found)


@mark.p3
def test_host_install_log(setup_host_install):
    """
    Checks that host_install produces the correct logs

    Setup:
        - Lock a compute node
        - Upload and apply a patch

    Test Steps:
        - Execute 'sw-patch host-install'
        - Check the log files for the expected logs

    Teardown:
        - Remove and delete the patch
        - Execute 'sw-patch host-install' again to update it to having no patches
        - Unlock compute

    """
    patch_name, host = setup_host_install
    con_ssh = ControllerClient.get_active_controller()

    con_ssh.exec_sudo_cmd('sw-patch host-install {}'.format(host), expect_timeout=timeout.CLI_TIMEOUT)
    res = check_install(host)
    assert res, "FAIL: The patch was not in \"sw-patch query-hosts\""

    search_for = ['sw-patch-controller-daemon.*INFO: Running host-install for {}'.format(host),
                  'sw-patch-controller-daemon.*INFO.*Patch installation request sent to {}'.format(host)]
    res = check_logs(search_for, lines=50, api=False)
    assert res, "FAIL: uploading patches did not generate the expected logs in patching.log"

    search_for = ['sw-patch-controller-daemon.*INFO: User: wrsroot/admin '
                  'Action: Running host-install for {}'.format(host)]
    res = check_logs(search_for, lines=25, api=True)
    assert res, "FAIL: uploading patches did not generate the expected logs in patching-api.log"
