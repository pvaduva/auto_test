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

    # Define test function level skip condition
    @mark.skipif(not system_helper.is_small_footprint(), reason="Only applies to small footprint lab.")
    # Use a number of test fixtures.
    # 'vms_': test function specific fixture. It will create a number of vms to ensure some vms are on the system when running the test, and delete all the created vms at the end of the test case
    # 'unlock_if_locked': test function specific fixture. It will unlock the locked host as part of test teardown
    # 'check_vms': system verification fixture, which checks the vms on the system before and after test run to ensure vms are still in good state after lock
    @mark.usefixtures('vms_', 'unlock_if_locked', 'check_vms')
    # Parametrize the test function generate two test cases: test lock active controller, test lock standby controller
    @mark.parametrize('host', [
        'active',
        'standby'
    ])
    # host which is named in mark.parametrize should be passed to test function as a parameter. pytest will report error if this is not done.
    def test_lock_unlock_small_footprint(self, host):
        """
        Test lock host on small footprint system
        
        Args:
            host: host to lock 
        
        Skip Conditions:
            - skip if standard system is discovered
        Test Setup:
            - Create a few vms for both tenant1 and tenant2
            - Record the status of VMs
        Test Steps:
            - Check whether lock request should be accepted. 
                i.e., lock should be accepted for standby controller and rejected for active controller
            - Verify lock is rejected for active controller and accepted for standby controller
        Test Teardown:
            - Check VMs status did not change
            - Unlock the host if host was locked successfully
        
        """
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
        code, output = host_helper.lock_host(host=target_host, fail_ok=True, check_first=False)

        self.lock_rtn_code = code
        self.target_host = target_host

        assert code in expt, output
