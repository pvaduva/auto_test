"""
This is for gathering key performance metrics related to installation.
"""
import time
from pytest import fixture, skip, mark
from utils.kpi import kpi_log_parser
from consts.proj_vars import ProjVar
from consts.kpi_vars import DRBDSync, ConfigController, LabSetup, HeatStacks, SystemInstall, NodeInstall, Idle
from keywords import system_helper, host_helper, cinder_helper, glance_helper, vm_helper
from utils.ssh import ControllerClient
from utils.tis_log import LOG


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


@mark.kpi
def test_idle_kpi(collect_kpi):
    if not collect_kpi:
        skip("KPI only test. Skip due to kpi collection is not enabled")

    LOG.tc_step("Delete vms and volumes on system if any")
    vm_helper.delete_vms()

    is_aio = system_helper.is_small_footprint()
    active_con = system_helper.get_active_controller_name()
    con_ssh = ControllerClient.get_active_controller()
    cpu_arg = ''
    if is_aio:
        LOG.info("AIO system found, check platform cores only")
        cpu_arg = ' -P '
        platform_cores_per_proc = host_helper.get_host_cpu_cores_for_function(hostname=active_con,
                                                                              function='Platform',
                                                                              core_type='log_core',
                                                                              thread=None, con_ssh=con_ssh)
        platform_cpus = []
        for proc in platform_cores_per_proc:
            platform_cpus += platform_cores_per_proc[proc]

        cpu_arg += ','.join([str(val) for val in platform_cpus])

    LOG.tc_step("Sleep for 5 minutes, then monitor for cpu and memory usage every 10 seconds for 5 minutes")
    # time.sleep(300)
    output = con_ssh.exec_cmd('sar -u{} 1 3 -r | grep --color=never "Average"'.format(cpu_arg),
                              expect_timeout=600, fail_ok=False)[1]

    # Sample output:
    # controller-1:~$ sar -u -P 0,1 1 3 -r | grep Average
    # Average:        CPU     %user     %nice   %system   %iowait    %steal     %idle
    # Average:          0      8.52      0.00      4.92      1.97      0.00     84.59
    # Average:          1     14.19      0.00      4.73      0.00      0.00     81.08
    # Average:    kbmemfree kbmemused  %memused kbbuffers  kbcached  kbcommit   %commit  kbactive   kbinact   kbdirty
    # Average:    105130499  26616873     20.20    203707    782956  63556293     48.24  24702756    529517       579

    lines = output.splitlines()

    # Parse mem usage stats
    mem_vals = lines.pop(-1).split()
    mem_headers = lines.pop(-1).split()
    mem_usage_index = mem_headers.index('%memused')
    mem_usage = float(mem_vals[mem_usage_index])

    # Parse cpu usage stats
    cpu_headers = lines.pop(0).split()
    cpu_lines = [line.split() for line in lines]
    idle_cpu_index = cpu_headers.index('%idle')
    cpus_idle = [float(cpu_vals[idle_cpu_index]) for cpu_vals in cpu_lines]
    avg_cpu_idle = sum(cpus_idle) / len(cpu_lines)
    avg_cpu_usage = round(100 - avg_cpu_idle, 4)

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=Idle.NAME_CPU, kpi_val=avg_cpu_usage, uptime=5,
                              unit='Percentage')

    kpi_log_parser.record_kpi(local_kpi_file=collect_kpi, kpi_name=Idle.NAME_MEM, kpi_val=mem_usage, uptime=5,
                              unit='Percentage')

