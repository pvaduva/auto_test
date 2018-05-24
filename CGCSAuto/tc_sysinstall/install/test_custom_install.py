import pytest

from keywords import install_helper
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def test_install(install_setup):
    lab_type = install_setup["lab"]["system_mode"]
    if "simplex" in lab_type:
        from tc_sysinstall.install.test_simplex_install import test_simplex_install
        LOG.debug("Starting simplex install")
        test_simplex_install(install_setup)
    elif "duplex" in lab_type:
        from tc_sysinstall.install.test_duplex_install import test_duplex_install
        LOG.debug("Starting duplex install")
        test_duplex_install(install_setup)
    elif "standard" in lab_type or "regular" in lab_type:
        from tc_sysinstall.install.test_standard_install import test_standard_install
        LOG.debug("Starting 2+2 install")
        test_standard_install(install_setup)
    elif "storage" in lab_type:
        from tc_sysinstall.install.test_storage_install import test_storage_install
        LOG.debug("Starting storage install")
        test_storage_install(install_setup)


def test_post_install():
    connection = ControllerClient.get_active_controller()

    rc = connection.exec_cmd("test -d /home/wrsroot/postinstall/")[0]
    if rc != 0:
        pytest.skip("No post install directory")
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg
    # TODO: unreserve lab