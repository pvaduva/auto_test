from utils.tis_log import LOG
from keywords import install_helper


def test_post_install_scripts(install_setup):
    active_controller = install_setup["active_controller"]
    if active_controller.ssh_conn is None:
        active_controller.ssh_conn = install_helper.establish_ssh_connection(active_controller.host_ip)
    rc = active_controller.ssh_conn.exec_cmd("test -d /home/wrsroot/postinstall/")
    if rc != 0:
        LOG.info("no post-fresh_install directory on {}".format(active_controller.name))
    else:
        rc, msg = install_helper.post_install()
        assert rc == 0, msg
