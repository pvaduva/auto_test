"""
This is for gathering key performance metrics related to installation.
"""

from pytest import fixture, skip, mark
from utils.kpi import kpi_log_parser
from consts.proj_vars import ProjVar
from consts.kpi_vars import DRBDSync, ConfigController, LabSetup, HeatStacks, SystemInstall, NodeInstall
from keywords import system_helper, host_helper, cinder_helper, glance_helper
from utils.ssh import ControllerClient


@fixture()
def drdb_precheck():
    """
    Skip test on simplex system.
    """

    if system_helper.is_simplex():
        skip("This test does not apply to single node systems")


@fixture()
def heat_precheck():
    """
    Skip test on systems that don't use heat stacks to setup the lab.
    """

    con_ssh = ControllerClient.get_active_controller()

    cmd = "test -f /home/wrsroot/.heat_resources"

    rc, out = con_ssh.exec_cmd(cmd)

    if rc != 0:
        skip("Heat is not used to setup this lab")


@mark.kpi
@mark.usefixtures("drdb_precheck")
def test_drbd_kpi(collect_kpi):
    """
    This test extracts the DRDB sync time from log files
    """

    if not collect_kpi:
        skip("KPI only test.  Skip due to kpi collection is not enabled")

    lab_name = ProjVar.get_var('LAB_NAME')
    log_path = DRBDSync.LOG_PATH
    kpi_name = DRBDSync.NAME
    end_pattern = DRBDSync.GREP_PATTERN
    python_pattern = DRBDSync.PYTHON_PATTERN

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=kpi_name,
                              log_path=log_path, python_pattern=python_pattern,
                              lab_name=lab_name, unit=DRBDSync.UNIT,
                              average_for_all=True, end_pattern=end_pattern, uptime=15)


@mark.kpi
def test_config_controller_kpi(collect_kpi):
    """
    This test extracts the time required to run config_controller.
    """

    if not collect_kpi:
        skip("KPI only test.  Skip due to kpi collection is not enabled")

    lab_name = ProjVar.get_var("LAB_NAME")
    log_path = ConfigController.LOG_PATH
    kpi_name = ConfigController.NAME
    host = "controller-0"
    start_pattern = ConfigController.START
    end_pattern = ConfigController.END

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=kpi_name,
                              log_path=log_path, lab_name=lab_name, host=host,
                              start_pattern=start_pattern,
                              end_pattern=end_pattern, sudo=True, topdown=True, uptime=15)


@mark.kpi
def test_lab_setup_kpi(collect_kpi):
    """
    This test extracts the time required to run lab_setup.sh only.
    """

    if not collect_kpi:
        skip("KPI only test.  Skip due to kpi collection is not enabled")

    lab_name = ProjVar.get_var("LAB_NAME")
    log_path = LabSetup.LOG_PATH
    kpi_name = LabSetup.NAME
    host = "controller-0"
    start_pattern = LabSetup.START
    end_pattern = LabSetup.END

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=kpi_name,
                              log_path=log_path, lab_name=lab_name, host=host,
                              start_pattern=start_pattern,
                              end_pattern=end_pattern, sudo=True, topdown=True, uptime=15)


@mark.kpi
@mark.usefixtures("heat_precheck")
def test_heat_kpi(collect_kpi):
    """
    Time to launch heat stacks.  Only applies to labs where .heat_resources is
    present.
    """

    if not collect_kpi:
        skip("KPI only test. Skip due to kpi collection is not enabled")

    lab_name = ProjVar.get_var("LAB_NAME")
    log_path = HeatStacks.LOG_PATH
    kpi_name = HeatStacks.NAME
    host = "controller-0"
    start_pattern = HeatStacks.START
    end_pattern = HeatStacks.END

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=kpi_name,
                              log_path=log_path, lab_name=lab_name, host=host,
                              start_pattern=start_pattern,
                              end_pattern=end_pattern, sudo=True, topdown=True,
                              start_pattern_init=True, uptime=15)


@mark.kpi
def test_system_install_kpi(collect_kpi):
    """
    This is the time to install the full system from beginning to end.

    Caveat is that it is designed to work with auto-install due to the way the
    end_pattern is constructed.
    """

    if not collect_kpi:
        skip("KPI only test. Skip due to kpi collection is not enabled")

    lab_name = ProjVar.get_var("LAB_NAME")
    host = "controller-0"
    kpi_name = SystemInstall.NAME
    log_path = SystemInstall.LOG_PATH
    start_pattern = SystemInstall.START
    start_path = SystemInstall.START_PATH
    end_pattern = SystemInstall.END

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=kpi_name, 
                              log_path=log_path, lab_name=lab_name, host=host,
                              start_pattern=start_pattern,
                              end_pattern=end_pattern, start_path=start_path,
                              sudo=True, topdown=True, start_pattern_init=True)


@mark.kpi
def test_node_install_kpi(collect_kpi):
    """
    This test measures the install time for each node in the system.
    """

    if not collect_kpi:
        skip("KPI only test. Skip due to kpi collection is not enabled")

    lab_name = ProjVar.get_var("LAB_NAME")
    hosts = system_helper.get_hostnames()
    print("System has hosts: {}".format(hosts))

    for host in hosts:
        kpi_name = NodeInstall.NAME.format(host)
        log_path = NodeInstall.LOG_PATH
        start_pattern = NodeInstall.START
        start_path = NodeInstall.START_PATH
        end_pattern = NodeInstall.END

        kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=kpi_name, 
                                log_path=log_path, lab_name=lab_name, host=host,
                                start_pattern=start_pattern,
                                end_pattern=end_pattern, start_path=start_path,
                                sudo=True, topdown=True, start_pattern_init=True)


