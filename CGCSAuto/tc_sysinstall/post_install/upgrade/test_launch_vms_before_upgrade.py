from consts.auth import Tenant
from consts.proj_vars import ProjVar
from keywords import system_helper, vm_helper, nova_helper
from testfixtures.resource_mgmt import ResourceCleanup
from utils.clients.ssh import ControllerClient
from utils.tis_log import LOG


def test_launch_vms_pre_upgrade():
    """
    This test  creates pre-upgrade VMs if not created by lab automated installer.

    Args:


    Returns:

    """
    LOG.tc_step("Launching VMs  pre upgrade ...")
    lab = ProjVar.get_var('LAB')
    count = 2 if system_helper.is_aio_simplex() or system_helper.is_aio_system() else int(len(lab['compute_nodes']) * 2)
    vms = vm_helper.get_any_vms(all_tenants=True)
    exiting_count = len(vms)
    con_ssh = ControllerClient.get_active_controller()
    tenants = [Tenant.TENANT1['user'], Tenant.TENANT2['user']]
    openrc = "/etc/nova/openrc"
    current_version = system_helper.get_sw_version()

    for tenant in tenants:
        tenant_cred_file = '/home/wrsroot/openrc.{}'.format(tenant)
        tenant_passwd = Tenant.TENANT1['password'] if tenant == Tenant.TENANT1['user'] else Tenant.TENANT2['password']
        if '*' in tenant_passwd:
            index = tenant_passwd.index('*')
            tenant_passwd = tenant_passwd[:index] + '\\' + tenant_passwd[index:]

        cmd = "test -f {}".format(tenant_cred_file)
        if con_ssh.exec_cmd(cmd)[0] != 0:
            con_ssh.exec_cmd("cp {} {}".format(openrc, tenant_cred_file))
            if current_version < '17.07':
                tenant_passwd = tenant
            con_ssh.exec_cmd('sed -i -e "s#admin#{}#g" {}'.format(tenant, tenant_cred_file))
            con_ssh.exec_cmd('sed -i -e "s#\\(OS_PASSWORD\)=.*#\\1={}#g" {}'.format(tenant_passwd,  tenant_cred_file))

    if count > exiting_count:

        LOG.tc_step("Create or get a flavor without ephemeral or swap disks")
        flavor_1 = nova_helper.get_flavors(name='flv_rootdisk')
        flavor_1 = flavor_1[0] if flavor_1 else nova_helper.create_flavor('flv_rootdisk', cleanup='function')[1]

        LOG.tc_step("Create or get another flavor with ephemeral and swap disks")
        flavor_2 = nova_helper.get_flavors(name='flv_ephemswap', ephemeral=1)
        flavor_2 = flavor_2[0] if flavor_2 else nova_helper.create_flavor('flv_ephemswap', ephemeral=1, swap=512,
                                                                          cleanup='function')[1]

        for i in range(int(count - exiting_count)):
            LOG.tc_step("Boot vm1 from volume with flavor flv_rootdisk and wait for it to be pingable from NatBox")
            vm1_name = "vol_root_{}".format(i)

            ProjVar.set_var(SOURCE_OPENRC=True)
            vm1 = vm_helper.boot_vm(vm1_name, flavor=flavor_1, auth_info=Tenant.get('tenant1'), cleanup='function',
                                    reuse_vol=True)[1]
            vm_helper.wait_for_vm_pingable_from_natbox(vm1)
            vms.append(vm1)
            if len(vms) == count:
                break

            LOG.tc_step("Boot vm2 from volume with flavor flv_localdisk and wait for it to be pingable from NatBox")
            vm2_name = "vol_ephemswap_{}".format(i)
            vm2 = vm_helper.boot_vm(vm2_name, flavor=flavor_2, auth_info=Tenant.get('tenant1'), cleanup='function',
                                    reuse_vol=True)[1]
            vm_helper.wait_for_vm_pingable_from_natbox(vm2)
            vms.append(vm2)
            if len(vms) == count:
                break

    else:

        LOG.info("Verifying existing VMs are pingable : {} ".format(vms))
        vm_helper.ping_vms_from_natbox(vm_ids=vms)

    LOG.info("VMs are launched and running pre-upgrade")

