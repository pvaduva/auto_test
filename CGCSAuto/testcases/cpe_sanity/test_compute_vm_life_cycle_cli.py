# Copyright (c) 2013-2014 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.


from oslo_log import log as logging
from cgcstest.cli import cli_helpers
from cgcstest.cli import instance_helpers
from cgcstest.cli import network_helpers
from cgcstest.cli import base
from tempest.test import attr
import subprocess
from cgcstest.cli.test_helpers import log_wrap
from cgcstest.cli.ssh_to_port import SSHClientWithPort as ssh_client
from tempest import exceptions


LOG = logging.getLogger(__name__)


class ComputeVMLifeCycleCli(base.BaseWRCliTest):
    """Basic, simple VM life cycle test for Nova CLI client.

    Confirm basic operations with VM instances
    """
    ubuntu_vm_login = 'ubuntu'
    ubuntu_passwd = 'ubuntu'
    #natbox_ip = self.external_host_ip

    def setUp(self):
        """"""
        super(ComputeVMLifeCycleCli, self).setUp()
        self.table = self.parser.table(self.clients.sysinv('host-list'))
        self.computes_list = cli_helpers.get_active_computes(self.table)

        self.natbox_ip = self.external_host_ip
        self.natbox_usr = self.external_host_user
        self.natbox_passwd = self.external_host_passwd

    def check_process_exists(self, cmd_output=None, process_name=None,
                             existence='+'):
        count = 0
        lines = []
        for line in cmd_output.split('\n'):
            if process_name in line:
                count = count + 1
                lines.append(line)
        if existence == '+':
            LOG.debug('Expected process: %s' % lines)
            self.assertNotEqual(count, 0, "Expected process doen't exist")
        else:
            LOG.debug('Unxpected process: %s' % lines)
            #self.assertEqual(count, 0, "Unxpected process existence")

    def tearDown(self):
        """"""
        self.delete_booted_vms()
        super(ComputeVMLifeCycleCli, self).tearDown()

    @log_wrap
    @attr(type=['cgcs_sanity', 'smoke', 'testcase_435'])
    def test_435_launching_guest_instances_on_first_compute(self):
        """
        Test launching Guest instances (ubuntu) on 1st Compute

        nova boot --key_name=controller-0 --flavor=1
                  --availability-zone=nova-compute:compute-0
                  --nic net-id=<private_net_id> --nic net-id=<internal_net_id>
                  --image=ubuntu-precise-amd64 ubuntu-test
        nova boot --key_name=controller-0 --flavor=1
                  --availability-zone=nova-compute:compute-0
                  --nic net-id=<private_net_id> --nic net-id=<internal_net_id>
                  --image=ubuntu-precise-amd64 ubuntu-test-1
        Verification Steps
        1. lock all computes except first one
        2. boot 2 ubuntu VMs
        """
        vm_name1 = 'ubuntu-test'
        vm_name2 = 'ubuntu-test-1'
        image_name = 'ubuntu-precise-amd64'
        compute_name = self.computes_list[0]
        LOG.debug('Booting ubuntu image on first compute')
        instance_helpers.launch_instance_on_compute(self,
                                                    network_name='private',
                                                    flavor=2,
                                                    host_name=compute_name,
                                                    image_name=image_name,
                                                    instance_name1=vm_name1,
                                                    instance_name2=vm_name2)

    @log_wrap
    @attr(type=['cgcs_sanity', 'smoke', 'testcase_437'])
    def test_437_launching_guest_instances_on_second_compute(self):
        """
        Test launching Guest ubuntu instances on 2nd Compute

        Verification
        1. Boot 2 VMS with
        nova boot --key_name=controller-0 --flavor=1
                  --availability-zone=nova-compute:compute-1
                  --nic net-id=<public_net_id> --nic net-id=<internal_net_id>
                  --image=ubuntu-precise-amd64 ubuntu-test
        nova boot --key_name=controller-0 --flavor=1
                  --availability-zone=nova-compute:compute-1
                  --nic net-id=<public_net_id> --nic net-id=<internal_net_id>
                  --image=ubuntu-precise-amd64 ubuntu-test-1
        2. Verify VMs successfully boot
        """
        vm_name1 = 'ubuntu-test'
        vm_name2 = 'ubuntu-test-1'
        image_name = 'ubuntu-precise-amd64'
        comp_name = self.computes_list[1]
        LOG.debug('Booting ubuntu VM on second compute')
        instance_helpers.launch_instance_on_compute(self,
                                                    network_name='private',
                                                    flavor=2,
                                                    host_name=comp_name,
                                                    image_name=image_name,
                                                    instance_name1=vm_name1,
                                                    instance_name2=vm_name2)

    @log_wrap
    @attr(type=['cgcs_sanity', 'smoke', 'testcase_438'])
    def test_438_launching_cgcs_guest_instances_on_second_compute(self):
        """
        Test launching Guest cgcs-guest instances on 2nd Compute

        Verification
        1. Boot 2 VMS with
        nova boot --key_name=controller-0 --flavor=1
                  --availability-zone=nova-compute:compute-1
                  --nic net-id=public_net_id --nic net-id=internal_net_id
                  --image=wrl5-avp wrl5-avp-test
        nova boot --key_name=controller-0 --flavor=1
                  --availability-zone=nova-compute:compute-1
                  --nic net-id=public_net_id --nic net-id=internal_net_id
                  --image=wrl5-avp wrl5-avp-test-1
        2. Verify VMs successfully boot
        """
        vm_name1 = 'wrl5-avp-test'
        vm_name2 = 'wrl5-avp-test1'
        comp_name = self.computes_list[1]
        LOG.debug('Booting cgcs_guest VM on second compute')
        instance_helpers.launch_instance_on_compute(self, network_name='public',
                                                    flavor=101,
                                                    host_name=comp_name,
                                                    image_name='wrl5-avp',
                                                    instance_name1=vm_name1,
                                                    instance_name2=vm_name2)

    @log_wrap
    @attr(type=['cgcs_regression', 'smoke', 'testcase_436',
                'cgcs_vm_lifecycle_test'])
    def test_436_confirm_no_process_deaths_or_unexpected_logs(self):
        """
        Confirm no process deaths or unexpected logs

        1. 'defunct' is not in processes, 'python' and 'postgres' are
                                                                in processes
        2. crm status (online controller, master name and status,
                    all services are started)
        """
        LOG.debug('Check processes')
        process_output = subprocess.check_output(["ps", "-eF"])
        self.check_process_exists(cmd_output=process_output,
                                  process_name="python", existence='+')
        self.check_process_exists(cmd_output=process_output,
                                  process_name="postgres", existence='+')
        self.check_process_exists(cmd_output=process_output,
                                  process_name="defunct", existence='-')

        LOG.debug('Execute sm-dump command')
        sm_dump_output = subprocess.check_output(["sm-dump"])
        sm_dict = cli_helpers.get_all_sm_dump_services_info(sm_dump_output)
        LOG.debug('Check online controllers')
        sda_list = self.parser.table(self.clients.sysinv('servicegroup-list'))
        master = cli_helpers.master_slave_info(sda_list, node_type='master')
        slave = cli_helpers.master_slave_info(sda_list, node_type='slave')
        expected_online_list = ['controller-0', 'controller-1']
        online_list = [master, slave]
        for element in online_list:
            if element is None:
                raise exceptions.NotFound("%s not found" % element)
        compare_list = list(set(online_list) & set(expected_online_list))
        self.assertGreaterEqual(len(compare_list), 2,
                                "Online list length is not equal to expected")

        LOG.debug('Check all services')
        error_services = []
        for service, info in sm_dict.items():
            if info["Service_state"] != "enabled-active":
                error_services.append(service)
            else:
                self.assertEqual(info["Service_state_desired"],
                                 "enabled-active",
                                 "Invalid desired service state")
        LOG.debug("Error service list: %s" % str(error_services))

        if error_services:
            for service in error_services:
                error_service_info = \
                    str(cli_helpers.get_sm_dump_info(sm_dump_output,
                                                     section='services',
                                                     search_param=service))
                LOG.debug("Error service - %s, info - %s"
                          % (service, error_service_info))
            raise Exception("Services in not Started state exist: %s"
                            % error_services)

    @log_wrap
    @attr(type=['cgcs_sanity', 'smoke', 'testcase_440'])
    def test_440_pause_unpause_delete_cgcs_instance(self):
        """
        Confirm can pause, unpause, delete VMs of cgcs-guest instances
        Verification Steps
        1. nova pause wrl5-avp-0
        2. nova unpause wrl5-avp-0
        3. nova delete wrl5-avp-0
        """
        LOG.debug('Boot cgcs-guest instance')
        ans = self.boot_vm(self, 'wrl5-avp', 'wrl5-avp-0')
        inst_id = ans['nova']['uuid']
        LOG.debug('Waiting untill VM state equals ACTIVE')
        instance_helpers.wait_until_instance_state_is_changed(self,
                                                              inst_id,
                                                              'ACTIVE',
                                                              timeout=360)
        LOG.debug('Pause-unpause VM of cgcs-guest instance')
        instance_helpers.execute_action(self, actions_list=['pause', 'unpause'],
                                        instance_name=inst_id)

        LOG.debug('Delete VM of cgcs-guest instance')

    @log_wrap
    @attr(type=['cgcs_sanity', 'smoke', 'testcase_444'])
    def test_444_vm_meta_data_retrieval(self):
        """
        VM meta-data retrieval

        ssh ubuntu@<vm_private_ip>
        wget http://169.254.169.254/latest/meta-data/instance-id
        """
        compute_name = self.computes_list[0]
        instance_helpers.lock_redundant_computes(self, self.computes_list, 1)
        LOG.debug('Booting ubuntu VM')
        ans = self.boot_vm(self, 'ubuntu-precise-amd64', 'ubuntu-0',
                           vif_model='e1000')
        inst_id = ans['nova']['uuid']
        LOG.debug('Waiting untill VM state equals ACTIVE')
        instance_helpers.wait_until_instance_state_is_changed(self, inst_id,
                                                              'ACTIVE',
                                                              timeout=360)
        # Get private IP address
        if self.check_tenant_exist():
            net_type = '-'.join([self.tenant.user, 'mgmt-net'])
        else:
            net_type = 'public-net0'
        vm_private_ip = instance_helpers.get_vm_ip_addr(self,
                                                        vm_name=inst_id,
                                                        network_type=net_type)
        LOG.debug('Define port value for ubuntu instance')
        port_value = network_helpers.define_port_value(self, 'ubuntu-0',
                                                       compute_name)
        LOG.debug('Waiting until VM answered on ping')
        network_helpers.wait_until_vm_answer_on_ping(self,
                                                     ip_addr=vm_private_ip)
        LOG.debug('Query meta-data')
        instance_id_output = \
            network_helpers.query_meta_data_from_vm(self.natbox_ip,
                                                    user=self.ubuntu_vm_login,
                                                    password=self.ubuntu_passwd,
                                                    port=port_value,
                                                    meta_data='instance-id')
        LOG.debug('Check instance-id meta-data')
        network_helpers.check_meta_data(self, instance_id_output, 'instance-id',
                                        inst_id)

    @log_wrap
    @attr(type=['cgcs_regression', 'smoke', 'testcase_446', 'degraded_retest',
                'cgcs_vm_lifecycle_test'])
    def test_446_vm_ubuntu_hard_reboot(self):
        """
        VM hard-reboot (ubuntu)

        nova reboot --hard ubuntu-0
        """
        LOG.debug('Boot ubuntu instance')
        ans = self.boot_vm(self, 'ubuntu-precise-amd64', 'ubuntu-0')
        inst_id = ans['nova']['uuid']
        LOG.debug('Waiting untill VM state equals ACTIVE')
        instance_helpers.wait_until_instance_state_is_changed(self, inst_id,
                                                              'ACTIVE',
                                                              timeout=360)
        LOG.debug('Execute hard reboot of instance')
        instance_helpers.reboot_instance(self, instance_name=inst_id,
                                         reboot_type='hard')

    @log_wrap
    @attr(type=['cgcs_regression', 'smoke', 'testcase_445', 'degraded_retest',
                'cgcs_vm_lifecycle_test'])
    def test_445_vm_ubuntu_soft_reboot(self):
        """
        VM soft-reboot (ubuntu)

        nova reboot ubuntu-0
        """
        LOG.debug('Boot ubuntu instance')
        ans = self.boot_vm(self, 'ubuntu-precise-amd64', 'ubuntu-0')
        inst_id = ans['nova']['uuid']
        LOG.debug('Waiting untill VM state equals ACTIVE')
        instance_helpers.wait_until_instance_state_is_changed(self, inst_id,
                                                              'ACTIVE',
                                                              timeout=360)
        LOG.debug('Execute hard reboot of instance')
        instance_helpers.reboot_instance(self, instance_name=inst_id,
                                         reboot_type='soft')

    @log_wrap
    @attr(type=['cgcs_regression', 'ha', 'smoke', 'testcase_512',
                'cgcs_vm_lifecycle_test', 'EAR2_PassThru_Regression'])
    def test_512_confirm_crm_status_comnd_and_validate_services_running(self):
        """
        With both controllers running, confirm crm_mon command and validate
                                all services running on at least one controller

        crm status

        Check:
            Online: [ controller-0 controller-1 ]
            All services are 'Started' with location 'controller-0'
        """
        LOG.debug('Execute sm-dump command')
        sm_dump_output = subprocess.check_output(["sm-dump"])
        sm_dict = cli_helpers.get_all_sm_dump_services_info(sm_dump_output)
        LOG.debug('Check online controllers')
        sda_list = self.parser.table(self.clients.sysinv('servicegroup-list'))
        master = cli_helpers.master_slave_info(sda_list, node_type='master')
        slave = cli_helpers.master_slave_info(sda_list, node_type='slave')
        expected_online_list = ['controller-0', 'controller-1']
        online_list = [master, slave]
        for element in online_list:
            if element is None:
                raise exceptions.NotFound("%s not found" % element)
        compare_list = list(set(online_list) & set(expected_online_list))
        self.assertGreaterEqual(len(compare_list), 2,
                                "Online list length is not equal to expected")

        LOG.debug('Check all services')
        error_services = []
        for service, info in sm_dict.items():
            if info["Service_state"] != "enabled-active":
                error_services.append(service)
            else:
                self.assertEqual(info["Service_state_desired"],
                                 "enabled-active",
                                 "Invalid desired service state")
        LOG.debug("Error service list: %s" % str(error_services))

        if error_services:
            for service in error_services:
                error_service_info = \
                    str(cli_helpers.get_sm_dump_info(sm_dump_output,
                                                     section='services',
                                                     search_param=service))
                LOG.debug("Error service - %s, info - %s"
                          % (service, error_service_info))
            raise Exception("Services in not Started state exist: %s"
                            % error_services)

    @log_wrap
    @attr(type=['cgcs_sanity', 'ceilometer', 'smoke', 'testcase_401'])
    def test_401_validate_ceilometer_meters_exist(self):
        """
        Validate ceilometer meters exist
        Verification Steps:
        1. Get ceilometer meter-list
        2. Check meters for router, subnet, image, and vswitch exists
        """
        LOG.debug('Get ceilometer meter-list')
        # By default upper limit is 500 lines; however router related lines are at 2000+. CGTS-3213
        # Increase the upper limit to 5000 lines.
        meter_table = self.parser.table(self.clients.ceilometer('meter-list', params=' -l 5000'))

        tables_list = ['neutron router-list', 'neutron subnet-list']

        LOG.debug('Check meters for router and subnet')
        for value in tables_list:
            table_name = value.split()[0]
            table_action = value.split()[1]
            table = self.parser.table(getattr(self.clients, table_name)(table_action))

            table_len = len(table['values'])
            LOG.debug("Table %s length is: %s" % (value, table_len))

            search_name = value.split()[1].split("-")[0]
            meters_num = \
                cli_helpers.get_number_of_elemnts_in_column(meter_table,
                                                            "Name",
                                                            search_name,
                                                            strict_match=True)
            LOG.debug("Number of elements in ceilometer table is: %s"
                      % meters_num)

            if meters_num >= table_len:
                match_flag = True
            else:
                match_flag = False

            self.assertEqual(
                match_flag, True,
                "Number of {} meters - {} is lower than table {} length - {}".format(
                    search_name, meters_num, value, table_len))

        LOG.debug('Check meters for image')
        image_table = self.parser.table(self.clients.nova('image-list'))
        for header in image_table["headers"]:
            if header == "ID":
                index_value = image_table["headers"].index(header)
        image_id_list = []
        for id_value in image_table['values']:
            LOG.debug("ID value is %s" % id_value[index_value])
            image_id_list.append(id_value[index_value])
        for id_value in image_id_list:
            meters_num = \
                cli_helpers.get_number_of_elemnts_in_column(meter_table,
                                                            "Resource ID",
                                                            id_value,
                                                            strict_match=True)
            self.assertNotEqual(meters_num, 0,
                                "No image resource IDs found.")

        LOG.debug('Check meters for vswitch')
        meters_num = \
            cli_helpers.get_number_of_elemnts_in_column(meter_table,
                                                        "Name",
                                                        "vswitch.engine.util",
                                                        strict_match=True)
        self.assertNotEqual(meters_num, 0,
                            "No vswitch resource IDs found.")

    @log_wrap
    @attr(type=['cgcs_sanity', 'ceilometer', 'smoke', 'testcase_402'])
    def test_402_validate_statistics_for_one_meter(self):
        """
        Validate statistics for one meter

        """
        # List with column names
        column_names_list = ['Count', 'Min', 'Max', 'Avg']

        LOG.debug('Get ceilometer statistics table')
        stats_table = self.parser.table(self.clients.ceilometer('statistics',
                                                        params='-m image.size'))
        # Get first table value in first column
        first_value = stats_table["values"][0][0]

        LOG.debug('Check that count, min, max, avg values are non-zero')
        for column_name in column_names_list:
            column_value = \
                cli_helpers.get_column_value_from_multiple_columns(stats_table,
                                                                   'Period',
                                                                   first_value,
                                                                   column_name)
            self.assertNotEqual(float(column_value), 0.0,
                                "Parameter %s value is equal to 0"
                                % column_name)

    @log_wrap
    @attr(type=['cgcs_sanity', 'sysinv', 'smoke', 'testcase_584'])
    def test_584_launch_vm_confirm_boot_and_login(self):
        """
        Verification
        1. Launch a VM with the supported wrl guest image
        2. Confirm boot and log in
        """
        LOG.debug('Boot cgcs-guest instance')
        ans = self.boot_vm(self, 'wrl5-avp', 'wrl5-avp-test')
        inst_id = ans['nova']['uuid']
        LOG.debug('Waiting untill VM state equals ACTIVE')
        instance_helpers.wait_until_instance_state_is_changed(self,
                                                              inst_id,
                                                              'ACTIVE',
                                                              timeout=360,
                                                              delay=3)

        vm_detail_tab = self.parser.table(self.clients.nova('show',
                                                    params=inst_id))
        vm_host_val = cli_helpers.get_column_value(vm_detail_tab,
                                                   'host')

        port_value = network_helpers.define_port_value(self, 'wrl5-avp-test',
                                                       vm_host_val)
        LOG.debug("SSH to VM instance via NATBox")
        ssh_conn = ssh_client(self.external_host_ip, 'root', 'root',
                              port_value)
        ssh_conn.test_connection_auth()
