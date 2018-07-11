import time
import ipaddress
from pytest import fixture, mark
from contextlib import contextmanager, ExitStack
from consts.auth import Tenant
from consts.filepaths import IxiaPath
from utils import cli, table_parser
from testfixtures.fixture_resources import ResourceCleanup
from utils.tis_log import LOG
from keywords import network_helper, vm_helper, common, nova_helper


@mark.parametrize('vm_type', [
    'virtio',
    'avp',
    'dpdk'
])
class TestPacketTypeSecurityRuleEnforcement(object):
    @fixture(scope='class')
    def security_groups(self):
        LOG.fixture_step("(class) Create two security groups")

        sg_primary = network_helper.create_security_group(
            "test_pkt_typ_sec_rul_enf", auth_info=Tenant.get_primary(), cleanup='class')
        sg_secondary = network_helper.create_security_group(
            "test_pkt_typ_sec_rul_enf", auth_info=Tenant.get_secondary(), cleanup='class')

        # required by ping_vms
        cli.openstack("security group rule create",
            "--protocol icmp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_primary), auth_info=Tenant.ADMIN)
        cli.openstack("security group rule create",
            "--protocol icmp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_secondary), auth_info=Tenant.ADMIN)

        # required by routing and ssh (TCP), could be restricted to ranges over internal-network and mgmt-network
        cli.openstack("security group rule create",
            "--protocol tcp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_primary), auth_info=Tenant.ADMIN)
        cli.openstack("security group rule create",
            "--protocol tcp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_secondary), auth_info=Tenant.ADMIN)

        yield sg_primary, sg_secondary

    def test_apply_group_at_launch(self, vm_type, security_groups, ixia_supported):
        """
        Apply security group to VMs at launch time, verify the rules are enforced

        Test Steps:
            - Create a VM pair of vm_type NICs with security group to disallow UDP traffic
            - Setup UDP traffic between vm_pair
            - Verify packets can not be received

        Test Teardown:
            - Stop traffic
            - Delete vms, volumes, flavor, security groups created
        """
        sg_primary, sg_secondary = security_groups

        vm_test, vm_observer = vm_helper.launch_vm_pair(vm_type,
            primary_kwargs=dict(sec_group_name=sg_primary),
            secondary_kwargs=dict(sec_group_name=sg_secondary))

        with vm_helper.traffic_between_vms([(vm_test, vm_observer)], ixncfg=IxiaPath.CFG_UDP) as session:
            LOG.tc_step("Verify UDP traffic is not allowed")
            succ, val = common.wait_for_val_from_func(0, 30, 5, session.get_frames_delta)
            assert not succ, "udp traffic successfully passed through"

    def test_apply_group_running_vm(self, vm_type, security_groups, ixia_supported):
        """
        Apply security group to VMs when the VMs are running, verify the rules are enforced

        Test Steps:
            - Create a VM pair of vm_type NICs
            - Apply security group to disallow UDP traffic
            - Setup UDP traffic between vm_pair
            - Verify packets can not be received

        Test Teardown:
            - Stop traffic
            - Delete vms, volumes, flavor, security groups created
        """
        sg_primary, sg_secondary = security_groups

        vm_test, vm_observer = vm_helper.launch_vm_pair(vm_type)

        LOG.tc_step("Add security groups to launched VMs")
        cli.nova('add-secgroup', "{} {}".format(vm_test, sg_primary), auth_info=Tenant.ADMIN)
        cli.nova('add-secgroup', "{} {}".format(vm_observer, sg_secondary), auth_info=Tenant.ADMIN)

        with vm_helper.traffic_between_vms([(vm_test, vm_observer)], ixncfg=IxiaPath.CFG_UDP) as session:
            LOG.tc_step("Verify UDP traffic is not allowed")
            succ, val = common.wait_for_val_from_func(0, 30, 5, session.get_frames_delta)
            assert not succ, "udp traffic successfully passed through"

    def test_modify_running_vm(self, vm_type, security_groups, ixia_supported):
        """
        Verify security_group related modifications are functioning as expected

        Test Steps:
            - Create a VM pair of vm_type NICs with security group to disallow UDP traffic
            - Verify security groups in use cannot be deleted
            - Setup UDP traffic between vm_pair
            - Verify packets can not be received
            - Add security group rules to allow UDP traffic
            - Verify packets can be received
            - Delete security group rules to disallow UDP traffic
            - Verify packets can not be received
            - Disassociate security group with VMs
            - Verify packets can be received

        Test Teardown:
            - Stop traffic
            - Delete vms, volumes, flavor, security groups created
        """
        sg_primary, sg_secondary = security_groups

        vm_test, vm_observer = vm_helper.launch_vm_pair(vm_type,
            primary_kwargs=dict(sec_group_name=sg_primary),
            secondary_kwargs=dict(sec_group_name=sg_secondary))

        LOG.info("Delete security group associated with running VM, verify it fails")
        code, output = network_helper.delete_security_group(sg_primary, fail_ok=True)
        LOG.info(output)
        assert code, "in-use security group {} deletion succeeded".format(sg_primary)
        code, output = network_helper.delete_security_group(sg_secondary, fail_ok=True)
        LOG.info(output)
        assert code, "in-use security group {} deletion succeeded".format(sg_secondary)

        with vm_helper.traffic_between_vms([(vm_test, vm_observer)], ixncfg=IxiaPath.CFG_UDP) as session:
            LOG.tc_step("Verify UDP traffic is not allowed")
            succ, val = common.wait_for_val_from_func(0, 30, 5, session.get_frames_delta)
            assert not succ, "udp traffic successfully passed through"

            LOG.tc_step("Allow UDP traffic on the fly and verify traffic comes back to normal")
            with udp_allow(*security_groups) as modified_groups:
                session.get_frames_delta(stable=True)   # raises if the delta is increasing (i.e., udp denied)

            LOG.tc_step("Verify UDP traffic is no longer allowed")
            succ, val = common.wait_for_val_from_func(0, 30, 5, session.get_frames_delta)
            assert not succ, "udp traffic successfully passed through"

            LOG.tc_step("Disassociate the security group, verify UDP traffic is allowed")
            cli.openstack("server remove security group {} {}".format(vm_test, sg_primary), auth_info=Tenant.ADMIN)
            cli.openstack("server remove security group {} {}".format(vm_observer, sg_secondary), auth_info=Tenant.ADMIN)
            session.get_frames_delta(stable=True)


@mark.parametrize('tenant', [
    'tenant1',
    'tenant2',
])
def test_max_reached_creation_fail(tenant):
    """
    Verify security group and security group rule quotas are respected

    Test Steps:
        - Retrieve security group and security group rule quota
        - Retrieve # of security groups in use
        - Create enough security groups to reach the quota
        - Verify creation fails
        - Retrieve $ of security group rules in use
        - Create enough security group rules to reach the quota
        - Verify creation fails

    Test Teardown:
        - Delete security groups created
    """
    if tenant == 'tenant1':
        auth_info = Tenant.TENANT1
    elif tenant == 'tenant2':
        auth_info = Tenant.TENANT2

    # nova_helper.get_quotas uses nova quota-show, which does not include secgroup* fields
    LOG.tc_step("Retrive quota and usage information")
    quota_table = table_parser.table(cli.openstack('quota show', auth_info=auth_info))
    max_secgroups = int(table_parser.get_value_two_col_table(quota_table, 'secgroups'))
    max_rules = int(table_parser.get_value_two_col_table(quota_table, 'secgroup-rules'))
    LOG.info("Tenant Quota Retrieved: secgroups={} secgroup-rules={}".format(max_secgroups, max_rules))

    LOG.tc_step("Retrieve usage for security groups")
    groups_list = table_parser.table(cli.openstack('security group list', auth_info=auth_info))
    in_use_secgroups = len(table_parser.get_all_rows(groups_list))
    LOG.info("Tenant InUse Retrieved: secgroups={}".format(in_use_secgroups))

    LOG.tc_step("Create enough groups to reach the quota")
    for i in range(max_secgroups - in_use_secgroups):
        # take the last security group for rules creation
        sec_group = network_helper.create_security_group('test_max_reached_creation_fail', auth_info=auth_info)

    LOG.tc_step("Verify security group creation fail as quota is reached")
    code, msg = network_helper.create_security_group(
        'test_max_reached_creation_fail', auth_info=auth_info, fail_ok=True)
    assert code, "creation after max quota reached succeeded"

    LOG.tc_step("Retrieve usage for security group rules")
    # note: each new security group creates 2 default rules for egress
    # therefore this usage must be retrieved after security group operations are completed
    rules_list = table_parser.table(cli.openstack('security group rule list', auth_info=auth_info))
    in_use_rules = len(table_parser.get_all_rows(rules_list))
    LOG.info("Tenant InUse Retrieved: secgroups-rules={}".format(in_use_rules))

    LOG.tc_step("Create enough rules to reach the quota")
    dummy_ip = ipaddress.ip_address("0.0.0.0")
    for i in range(max_rules - in_use_rules):
        dummy_ip += 1   # duplicate security group rule creation will fail
        cli.openstack(
            "security group rule create", "--protocol udp --remote-ip {}/32 --ingress {}".format(
                dummy_ip, sec_group),
            auth_info=auth_info)
    LOG.tc_step("Verify security rule creation fail as quota is reached")
    code, msg = cli.openstack(
        "security group rule create", "--protocol udp --remote-ip 255.255.255.254/32 --ingress {}".format(
            sec_group),
        auth_info=auth_info, fail_ok=True)
    assert code, "creation after max quota reached succeeded"


@contextmanager
def udp_allow(sg_primary, sg_secondary):
    LOG.info("Creating rules to allow UDP ingress for {} and {}".format(sg_primary, sg_secondary))
    table = table_parser.table(
        cli.openstack(
            "security group rule create", "--protocol udp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_primary),
            auth_info=Tenant.ADMIN))
    udp_primary = table_parser.get_value_two_col_table(table, 'id')

    table = table_parser.table(
        cli.openstack(
            "security group rule create", "--protocol udp --remote-ip 0.0.0.0/0 --ingress {}".format(sg_secondary),
            auth_info=Tenant.ADMIN))
    udp_secondary = table_parser.get_value_two_col_table(table, 'id')

    yield sg_primary, sg_secondary

    LOG.info("Deleting UDP ingress rules for {} and {}".format(sg_primary, sg_secondary))
    cli.openstack("security group rule delete", udp_primary, auth_info=Tenant.ADMIN)
    cli.openstack("security group rule delete", udp_secondary, auth_info=Tenant.ADMIN)

