from utils.tis_log import LOG
from utils import exceptions, table_parser
from keywords import host_helper, system_helper

# Remove following tests as functionality already covered in various nova testcases

def test_show_cpu_data():
    """
    TC684
    Verify that CPU data can be retrieved through the cli

    Test Steps:
        - Get a list of all hosts
        - List cpu data for each host
        - Verify that the data is in a valid form

    """
    hosts = host_helper.get_hosts()
    for host in hosts:
        if host == 'None':
            continue
        LOG.tc_step("Getting cpu data for host: {}".format(host))
        table_ = system_helper.get_host_cpu_list_table(host=host)

        for core in table_['values']:
            log_core = core[1]
            table_2 = system_helper.get_host_cpu_show_table(host=host, proc_num=log_core)

            uuid_1 = table_parser.get_values(table_, 'uuid', strict=True, log_core=log_core)[0]
            uuid_2 = table_parser.get_value_two_col_table(table_2, 'uuid')
            assert uuid_1 == uuid_2, "FAIL: Different uuid from each table"

            proc_1 = table_parser.get_values(table_, 'processor', strict=True, log_core=log_core)[0]
            proc_2 = table_parser.get_value_two_col_table(table_2, 'processor (numa_node)')
            assert 0 <= int(proc_1) == int(proc_2), "FAIL: The processor value is invalid"

            phy_1 = table_parser.get_values(table_, 'phy_core', strict=True, log_core=log_core)[0]
            phy_2 = table_parser.get_value_two_col_table(table_2, 'physical_core')
            assert 0 <= int(phy_1) == int(phy_2), "FAIL: The phy_core value is invalid"

            functions = ['Platform', 'vSwitch', 'Shared', 'VMs']
            funct_1 = table_parser.get_values(table_, 'assigned_function', strict=True, log_core=log_core)[0]
            funct_2 = table_parser.get_value_two_col_table(table_2, 'assigned_function')
            assert funct_1 == funct_2 and funct_1 in functions, "FAIL: The assigned_function value is invalid"


def test_show_mem_data():
    """
    TC687
    Verify that memory data can be seen through the cli
    Test Steps:
        - Get a list of all hosts
        - Show memory data for each host in different forms
        - Verify the memory data is in a valid form and that the different forms match

    """
    hosts = host_helper.get_hosts()
    for host in hosts:
        if host == 'None':
            continue
        LOG.tc_step("Getting memory data for host: {}".format(host))
        table_ = system_helper.get_host_mem_list(host=host)

        for processor in table_['values']:
            proc = processor[0]
            assert 0 <= int(proc), "FAIL: The processor value is invalid"

            mem_tot = table_parser.get_values(table_, 'mem_total(MiB)', strict=True, processor=proc)[0]
            assert 0 <= int(mem_tot), "FAIL: This host has no memory with its processor"
            mem_avail = table_parser.get_values(table_, 'mem_avail(MiB)', strict=True, processor=proc)[0]
            assert 0 <= int(mem_avail) <= int(mem_tot), "FAIL: The memory available is an invalid value"
            hp = table_parser.get_values(table_, 'hugepages(hp)_configured', strict=True, processor=proc)[0]
            assert 'True' == hp or 'False' == hp, "FAIL: Neither True nor False"

            table_2 = system_helper.get_host_memory_table(host=host, proc_num=proc)
            total = table_parser.get_value_two_col_table(table_2, 'Memory:.*Total.*(MiB)', regex=True)
            assert mem_tot == total, "FAIL: The two tables don't agree on total memory"
            pages = table_parser.get_value_two_col_table(table_2, 'Huge Pages Configured')
            assert hp == pages, "FAIL: The two tables don't agree on huge pages configuration"
