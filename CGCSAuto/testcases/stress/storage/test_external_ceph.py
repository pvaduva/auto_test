"""
This test enables external ceph on a system after the systems are freshly
installed.  This feature is only supported on one lab at the moment, Wildcat-7-12
as the external ceph system and Wildcat-3-6 as the regular lab.

Once external ceph is enabled, it cannot be disabled.  Once external ceph is
added, all services that were added will default to being created in the
external ceph backend.

This test will:
1.  Enable external ceph
2.  Check that the new external ceph cinder type is created
3.  Attempt to create a volume and confirm that it defaults to the external
ceph backend

Once external ceph is added, standard regression tests can be run on the system
thereby utilizing the feature.
"""


from pytest import mark, skip

from consts.auth import HostLinuxCreds, Tenant
from consts.proj_vars import ProjVar
from consts.cgcs import BackendState
from keywords import cinder_helper, storage_helper
from utils import cli, table_parser
from utils.tis_log import LOG
from utils.clients.ssh import ControllerClient, SSHClient
from setups import get_lab_dict


def check_cinder_type(cinder_type="ceph-external-ceph-external"):
    """
    This function checks if a particular cinder type is now listed in the
    cinder type list.

    Args:
    - cinder_type (string) - what cinder type to look for.  e.g. ceph-external

    Returns:
    - (bool) True if type is found, False if not
    """

    table_ = table_parser.table(cli.cinder('type-list'))
    cinder_types = table_parser.get_values(table_, 'Name')

    return bool(cinder_type in cinder_types)


def check_external_ceph():
    """
    This function checks if external ceph is provisioned on a system.

    Arguments:
    - None

    Returns:
    - (bool) True if provisioned, False if not
    """

    table_ = table_parser.table(cli.system('storage-backend-list'))
    backends = table_parser.get_values(table_, 'backend')

    return bool('ceph-external' in backends)


def add_external_ceph(dest_filepath, ceph_services):
    """
    This function adds external ceph as a storage backend.  NOTE, this action
    cannot be undone.

    Arguments:
    - Takes the path to the external ceph.conf file as an argument.

    Returns:
    - Nothing

    Test Steps:
    - Check if external ceph has already been added.  If so, skip.
    - Otherwise, add external ceph
    - Once external ceph is added, controllers will go into configuring state
    - Wait until controllers are configured
    - Check that the cinder service list now includes external ceph
    - Launch a volume and ensure it now defaults to the external ceph backend
    - Volume clean up done via resource clean-up
    - Now system is ready to be used
    """

    LOG.tc_step('Check if external ceph has already been added')
    backend_provisioned = check_external_ceph()
    if backend_provisioned:
        skip('External ceph backend already configured')

    # User may provision all or a subset of ceph services to be external
    ceph_pools = ""
    if 'cinder' in ceph_services:
        ceph_pools += ' cinder_pool=cinder-volumes'
    if 'glance' in ceph_services:
        ceph_pools += ' glance_pool=images'
    if 'nova' in ceph_services:
        ceph_pools += ' ephemeral_pool=ephemeral'
    ceph_name = 'ceph-external'
    ceph_params = ",".join(ceph_services)

    LOG.tc_step('Add the external ceph backend')
    cmd = "storage-backend-add -s {} -n {} -c {} {} {}".format(ceph_params,
                                                               ceph_name, dest_filepath,
                                                               ceph_name, ceph_pools)
    cli.system(cmd)

    LOG.tc_step('Wait for the storage backend to go into configuring state')
    storage_helper.wait_for_storage_backend_vals(ceph_name, **{'state': BackendState.CONFIGURING})

    LOG.tc_step('Wait for the storage backend to become configured')
    storage_helper.wait_for_storage_backend_vals(ceph_name, **{'state': BackendState.CONFIGURED})

    # Need to confirm if we actually had a config out-of-date alarm

    LOG.tc_step('Check the expected cinder type is added')
    assert check_cinder_type(cinder_type="ceph-external-ceph-external"), "External ceph cinder type was not found"

    LOG.tc_step('Launch a volume and ensure it is created in the external ceph backend')
    vol_id = cinder_helper.create_volume(cleanup="function")[1]
    table_ = table_parser.table(cli.cinder('show', vol_id, auth_info=Tenant.get('admin')))
    volume_type = table_parser.get_value_two_col_table(table_, 'os-vol-host-attr:host', strict=False)
    assert volume_type == 'controller@ceph-external#ceph-external', "Volume created in wrong backend"


@mark.parametrize(('ceph_lab', 'ceph_services'),
                   [('WCP_7_12', ['cinder', 'glance', 'nova'])])
def test_configure_external_ceph(ceph_lab, ceph_services):
    """
    This test will configure external ceph on a system.  Currently this is only
    supported on wcp3-6, using wcp7-12 as the external ceph system.  In order
    to support this, the user will need to install wcp7-12 in Region mode, then
    wcp3-6 needs to be installed with a custom config that includes an
    infrastructure interface.

    The ceph.conf file needs to be then copied from wcp7-12 onto wcp3-6.  This
    conf file needs to be renamed to something other than ceph.conf and then used
    to enable external ceph.  Only the following services can be enabled on
    external ceph: cinder, nova and glance.  Swift is not supported.

    Once external ceph is enabled, a new cinder type will be added and
    resource creation will default to the external ceph backend (depending on what
    services were provisioned in the first place).

    Test Steps:
    1.  Copy ceph.conf from wcp7-12
    2.  Provision external ceph services on wcp3-6

    TODO:
    - Add an infra ping test from regular lab to ceph lab - skip if fails
    """

    LOG.tc_step("Retrieve ceph.conf from the external ceph system")

    con_ssh = ControllerClient.get_active_controller()

    source_server = get_lab_dict(ceph_lab)['floating ip']
    source_lab_name = get_lab_dict(ceph_lab)['short_name']
    dest_server = ProjVar.get_var('LAB').get('floating ip')

    source_filepath = "/etc/ceph/ceph.conf"
    dest_filepath = "/home/wrsroot/ceph_{}.conf".format(source_lab_name)

    con_ssh.scp_files(source_file=source_filepath, source_server=source_server,
                      source_password=HostLinuxCreds.get_password(),
                      source_user=HostLinuxCreds.get_user(), dest_file=dest_filepath,
                      dest_password=HostLinuxCreds.get_password(),
                      dest_server=dest_server, fail_ok=True)

    LOG.tc_step("Confirm ceph.conf file was successfully copied before proceeding")
    if not con_ssh.file_exists(dest_filepath):
        skip("External ceph.conf not present on the system")

    LOG.tc_step("Provision storage-backend for external ceph")
    add_external_ceph(dest_filepath, ceph_services)
