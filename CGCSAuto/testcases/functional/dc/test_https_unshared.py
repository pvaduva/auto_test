from pytest import fixture

from keywords import security_helper, keystone_helper, dc_helper
from utils import cli
from utils.tis_log import LOG
from consts.auth import Tenant
from consts.proj_vars import ProjVar


@fixture(scope='module')
def revert_https(request):
    central_auth = Tenant.get('admin_platform', dc_region='RegionOne')
    sub_auth = Tenant.get('admin_platform')

    origin_https_sub = keystone_helper.is_https_enabled(auth_info=sub_auth)
    origin_https_central = keystone_helper.is_https_enabled(auth_info=central_auth)

    def _revert():
        LOG.fixture_step("Revert central https config to {}.".format(origin_https_central))
        security_helper.modify_https(enable_https=origin_https_central, auth_info=central_auth)

        LOG.fixture_step("Revert subcloud https config to {}.".format(origin_https_sub))
        security_helper.modify_https(enable_https=origin_https_central, auth_info=sub_auth)

        LOG.fixture_step("Verify cli's on subcloud and central region.".format(origin_https_sub))
        verify_cli(sub_auth, central_auth)

    request.addfinalizer(_revert)

    return origin_https_sub, origin_https_central, central_auth, sub_auth


def test_dc_modify_https(revert_https):
    """
    Test enable/disable https

    Test Steps:
        - Ensure central region https to be different than subcloud
        - Wait for subcloud sync audit and ensure subcloud https is not changed
        - Verify cli's in subcloud and central region
        - Modify https on central and subcloud
        - Verify cli's in subcloud and central region

    Teardown:
        - Revert https config on central and subcloud

    """
    origin_https_sub, origin_https_central, central_auth, sub_auth = revert_https
    subcloud = ProjVar.get_var('PRIMARY_SUBCLOUD')

    new_https_sub = not origin_https_sub
    new_https_central = not origin_https_central

    LOG.tc_step("Ensure central region https to be different than {}".format(subcloud))
    security_helper.modify_https(enable_https=new_https_sub, auth_info=central_auth)

    LOG.tc_step("Wait for subcloud sync audit and ensure {} https is not changed".format(subcloud))
    dc_helper.wait_for_sync_audit(subclouds=subcloud)
    assert origin_https_sub == keystone_helper.is_https_enabled(auth_info=sub_auth), "HTTPS config changed in subcloud"

    LOG.tc_step("Verify cli's in {} and central region".format(subcloud))
    verify_cli(sub_auth, central_auth)

    if new_https_central != new_https_sub:
        LOG.tc_step("Set central region https to {}".format(new_https_central))
        security_helper.modify_https(enable_https=new_https_central, auth_info=central_auth)

    LOG.tc_step("Set {} https to {}".format(subcloud, new_https_sub))
    security_helper.modify_https(enable_https=new_https_sub, auth_info=sub_auth)

    LOG.tc_step("Verify cli's in {} and central region after https modify on subcloud".format(subcloud))
    verify_cli(sub_auth, central_auth)


def verify_cli(sub_auth=None, central_auth=None):
    auths = [central_auth, sub_auth]
    auths = [auth for auth in auths if auth]

    for auth in auths:
        cli.system('host-list', fail_ok=False, auth_info=auth)
        cli.fm('alarm-list', fail_ok=False, auth_info=auth)
        cli.openstack('server list --a', fail_ok=False, auth_info=auth)
        cli.openstack('image list', fail_ok=False, auth_info=auth)
        cli.openstack('volume list --a', fail_ok=False, auth_info=auth)
        cli.openstack('user list', fail_ok=False, auth_info=auth)
        cli.openstack('router list', fail_ok=False, auth_info=auth)

    if sub_auth:
        cli.openstack('stack list', fail_ok=False, auth_info=sub_auth)
        cli.openstack('alarm list', fail_ok=False, auth_info=sub_auth)
        cli.openstack('metric status', fail_ok=False, auth_info=sub_auth)
