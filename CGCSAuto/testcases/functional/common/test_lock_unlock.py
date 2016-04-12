from pytest import mark, fixture

from utils import table_parser, cli
from utils.tis_log import LOG
from consts.auth import Tenant
from keywords import vm_helper, host_helper, nova_helper, system_helper


@fixture(scope='module')
def vms_(request):
    vms_tenant1 = vm_helper.get_any_vms(count=2, auth_info=Tenant.TENANT_1, rtn_new=True)
    vms_tenant2 = vm_helper.get_any_vms(count=2, auth_info=Tenant.TENANT_2, rtn_new=True)

    def delete_vms():
        for vm in vms_tenant1[1]:
            vm_helper.delete_vm(vm, fail_ok=True, auth_info=Tenant.TENANT_1)
        for vm in vms_tenant2[1]:
            vm_helper.delete_vm(vm, fail_ok=True, auth_info=Tenant.TENANT_2)
    request.addfinalizer(delete_vms)

    return [vms_tenant1[0], vms_tenant2[0]]


class TestLockUnlock:
    @fixture()
    def unlock_if_locked(self, request):
        self.lock_rtn_code = None
        self.target_host = None

        def unlock():
            if self.lock_rtn_code in [0, 3]:
                host_helper.unlock_host(self.target_host)
        request.addfinalizer(unlock)

    @mark.skipif(system_helper.is_small_footprint(), reason="Skip for small footprint lab")
    @mark.usefixtures('vms_', 'unlock_if_locked')
    def test_lock_unlock_vm_host(self):

        # Gather system info to determine expected result:
        # has_vm = bool(nova_helper.get_all_vms())
        table_hypervisors = table_parser.table(cli.nova('hypervisor-list', auth_info=Tenant.ADMIN))
        all_hypervisors = table_parser.get_column(table_hypervisors, 'Hypervisor hostname')
        up_hypervisors = table_parser.get_values(table_hypervisors, 'Hypervisor hostname', Status='enabled', State='up')

        LOG.tc_step("Calculate target host...")
        hypervisors_vms = nova_helper.get_vms_by_hypervisors()
        hypervisors = list(hypervisors_vms.keys())
        vms = list(hypervisors_vms.values())
        max_vms = max(list(hypervisors_vms.values()), key=len)
        target_host = hypervisors[vms.index(max_vms)]

        # TODO: what if target_host is not one of the up_hypervisors??

        LOG.tc_step("Gather vms info and calculate expected result...")
        pre_vms_status = nova_helper.get_vms_info(header='Status')

        if len(all_hypervisors) < 2:
            expt = 1
        elif len(up_hypervisors) < 2:
            expt = 2
        else:
            expt = 0

        LOG.tc_step("Attempt to lock {}. Expected return code: {}".format(target_host, expt))
        code, output = host_helper.lock_host(host=target_host, fail_ok=True, check_bf_lock=False)
        self.lock_rtn_code = code
        self.target_host = target_host

        assert code == expt, output

        LOG.tc_step("Verify vms status after lock attempt...")
        post_vms_status = nova_helper.get_vms_info(header='Status')

        failure_msgs = []
        if not pre_vms_status == post_vms_status:
            for vm, post_status in post_vms_status:
                if post_status.lower() != 'active' and post_status != pre_vms_status[vm]:
                    msg = "VM {} is not in good state after lock. Pre status: {}. Post status: {}".\
                        format(vm, pre_vms_status[vm], post_status)
                    failure_msgs.append(msg)

        assert not failure_msgs, '\n'.join(failure_msgs)
    
    @mark.skipif(not system_helper.is_small_footprint(), reason="Only applies to small footprint lab.")
    @mark.usefixtures('vms_', 'unlock_if_locked', 'check_vms')
    @mark.parametrize('host', [
        'active',
        'standby'
    ])
    def test_lock_unlock_small_footprint(self, host):
        LOG.tc_step("Calculate expected result...")
        hosts = ['controller-0', 'controller-1']
        active_con = system_helper.get_active_controller_name()
        standby_con = system_helper.get_standby_controller_name()
        if host == 'standby':
            hosts.remove(active_con)
            target_host = hosts[0]
            if standby_con:
                expt = [0]
            else:
                expt = [1, 2]
        else:
            target_host = active_con
            expt = [1]

        LOG.tc_step("Attempt to lock {}...".format(target_host))
        code, output = host_helper.lock_host(host=target_host, fail_ok=True, check_bf_lock=False)

        self.lock_rtn_code = code
        self.target_host = target_host

        assert code in expt, output
