from pytest import fixture
from utils.tis_log import LOG
from keywords import system_helper, install_helper, storage_helper

from testfixtures.resource_mgmt import ResourceCleanup
from keywords import vm_helper, nova_helper, host_helper, cinder_helper

from consts.proj_vars import ProjVar
from consts.auth import Tenant


@fixture(scope='function')
def vms_with_upgrade():
    """
    Test test_vms_with_upgrade is for create various vms before upgrade

    Skip conditions:
        - Less than two hosts configured with storage backing under test

    Setups:
        - Add admin role to primary tenant (module)

    Test Steps:
        - Create flv_rootdisk without ephemeral or swap disks, and set storage backing extra spec
        - Create flv_ephemswap with ephemeral AND swap disks, and set storage backing extra spec
        - Boot following vms  and wait for them to be pingable from NatBox:
            - Boot vm1 from volume with flavor flv_rootdisk
            - Boot vm2 from volume with flavor flv_localdisk
            - Boot vm3 from image with flavor flv_rootdisk
            - Boot vm4 from image with flavor flv_rootdisk, and attach a volume to it
            - Boot vm5 from image with flavor flv_localdisk
        - sudo reboot -f on vms host

    Teardown:
        - Delete created vms, volumes, flavors

    """
    LOG.fixture_step("Create a flavor without ephemeral or swap disks")
    flavor_1 = nova_helper.create_flavor('flv_rootdisk', check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor_1)

    LOG.fixture_step("Create another flavor with ephemeral and swap disks")
    flavor_2 = nova_helper.create_flavor('flv_ephemswap', ephemeral=1, swap=1, check_storage_backing=False)[1]
    ResourceCleanup.add('flavor', flavor_2)

    LOG.fixture_step("Boot vm1 from volume with flavor flv_rootdisk and wait for it pingable from NatBox")
    vm1_name = "vol_root"
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.TENANT2)
    vm1 = vm_helper.boot_vm(vm1_name, flavor=flavor_1, auth_info=Tenant.TENANT2)[1]
    ResourceCleanup.add('vm', vm1, del_vm_vols=True )

    LOG.fixture_step("Boot vm2 from volume with flavor flv_localdisk and wait for it pingable from NatBox")
    vm2_name = "vol_ephemswap"
    vm2 = vm_helper.boot_vm(vm2_name, flavor=flavor_2, auth_info=Tenant.TENANT2)[1]
    ResourceCleanup.add('vm', vm2, del_vm_vols=True )

    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)
    vm_helper.wait_for_vm_pingable_from_natbox(vm1)
    vm_helper.wait_for_vm_pingable_from_natbox(vm2)
    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.TENANT2)

    LOG.fixture_step("Boot vm3 from image with flavor flv_rootdisk and wait for it pingable from NatBox")
    vm3_name = "image_root"
    vm3 = vm_helper.boot_vm(vm3_name, flavor=flavor_1, auth_info=Tenant.TENANT2)[1]
    ResourceCleanup.add('vm', vm3, del_vm_vols=True)

    LOG.fixture_step("Boot vm4 from image with flavor flv_rootdisk, attach a volume to it and wait for it "
                "pingable from NatBox")
    vm4_name = 'image_root_attachvol'
    vm4 = vm_helper.boot_vm(vm4_name, flavor_1, auth_info=Tenant.TENANT2)[1]
    ResourceCleanup.add('vm', vm4, del_vm_vols=True)

    vol = cinder_helper.create_volume(bootable=False)[1]
    ResourceCleanup.add('volume', vol)
    vm_helper.attach_vol_to_vm(vm4, vol_id=vol)

    LOG.fixture_step("Boot vm5 from image with flavor flv_localdisk and wait for it pingable from NatBox")
    vm5_name = 'image_ephemswap'
    vm5 = vm_helper.boot_vm(vm5_name, flavor_2, source='image', auth_info=Tenant.TENANT2)[1]
    ResourceCleanup.add('vm', vm5, del_vm_vols=True)

    ProjVar.set_var(SOURCE_CREDENTIAL=Tenant.ADMIN)

    vm_helper.wait_for_vm_pingable_from_natbox(vm4)
    vm_helper.wait_for_vm_pingable_from_natbox(vm5)

    vms = [vm1, vm2, vm3, vm4, vm5]
    return vms

def test_system_upgrade(vms_with_upgrade, upgrade_setup, check_system_health_query_upgrade):

    LOG.info("Boot VM before upgrade ")
    vms=vms_with_upgrade
    vm_helper.ping_vms_from_natbox(vms)
    lab = upgrade_setup['lab']
    current_version = upgrade_setup['current_version']
    upgrade_version = upgrade_setup['upgrade_version']

    force = False
    LOG.tc_step("Checking system health for upgrade .....")
    if check_system_health_query_upgrade[0] == 0:
        LOG.info("System health OK for upgrade......")
    elif check_system_health_query_upgrade[0] == 2:
        LOG.info("System health indicate minor alarms; using --force option to start upgrade......")
        force = True
    else:
        assert False, "System health query upgrade failed: {}".format(check_system_health_query_upgrade[1])

    LOG.tc_step("Starting upgrade from release {} to target release {}".format(current_version, upgrade_version))
    system_helper.system_upgrade_start(force=force)
    LOG.info("upgrade started successfully......")

    # upgrade standby controller
    LOG.tc_step("Upgrading controller-1")
    host_helper.upgrade_host("controller-1", lock=True)
    LOG.info("Host controller-1 is upgraded successfully......")

    vm_helper.ping_vms_from_natbox(vms)
    # unlock upgraded controller-1
    LOG.tc_step("Unlocking controller-1 after upgrade......")
    host_helper.unlock_host("controller-1", available_only=True, check_hypervisor_up=False)
    LOG.info("Host controller-1 unlocked after upgrade......")

    # Swact to standby controller-1
    LOG.tc_step("Swacting to controller-1 .....")
    rc, output = host_helper.swact_host(hostname="controller-0")
    assert rc == 0, "Failed to swact: {}".format(output)
    LOG.info("Swacted and  controller-1 has become active......")

    active_controller = system_helper.get_active_controller_name()

    # upgrade  controller-0
    LOG.tc_step("Upgrading  controller-0......")
    controller0 = lab['controller-0']

    LOG.info("Ensure controller-0 is provisioned before upgrade.....")
    host_helper.ensure_host_provisioned(controller0.name)
    LOG.info("Host {} is provisioned for upgrade.....".format(controller0.name))

    # open vlm console for controller-0 for boot through mgmt interface
    LOG.info("Opening a vlm console for controller-0 .....")
    install_helper.open_vlm_console_thread("controller-0")

    LOG.info("Starting {} upgrade.....".format(controller0.name))
    host_helper.upgrade_host(controller0.name, lock=True)
    LOG.info("controller-0 is upgraded successfully.....")

    # unlock upgraded controller-0
    LOG.tc_step("Unlocking controller-0 after upgrade......")
    host_helper.unlock_host(controller0.name, available_only=True)
    LOG.info("Host {} unlocked after upgrade......".format(controller0.name))
    vm_helper.ping_vms_from_natbox(vms)
    upgrade_hosts = install_helper.get_non_controller_system_hosts()
    LOG.info("Starting upgrade of the other system hosts: {}".format(upgrade_hosts))

    for host in upgrade_hosts:
        LOG.tc_step("Starting {} upgrade.....".format(host))
        if "storage" in host:
            # wait for replication  to be healthy
            storage_helper.wait_for_ceph_health_ok()

        host_helper.upgrade_host(host, lock=True)
        LOG.info("{} is upgraded successfully.....".format(host))
        LOG.tc_step("Unlocking {} after upgrade......".format(host))
        host_helper.unlock_host(host, available_only=True)
        LOG.info("Host {} unlocked after upgrade......".format(host))
        LOG.info("Host {} upgrade complete.....".format(host))
        vm_helper.ping_vms_from_natbox(vms)

    # Activate the upgrade
    LOG.tc_step("Activating upgrade....")
    system_helper.activate_upgrade()
    LOG.info("Upgrade activate complete.....")

    # Make controller-0 the active controller
    # Swact to standby controller-0
    LOG.tc_step("Making controller-0 active.....")
    rc, output = host_helper.swact_host(hostname="controller-1")
    assert rc == 0, "Failed to swact: {}".format(output)
    LOG.info("Swacted to controller-0 ......")

    # Complete upgrade
    LOG.tc_step("Completing upgrade from  {} to {}".format(current_version, upgrade_version))
    system_helper.complete_upgrade()
    LOG.info("Upgrade is complete......")

    LOG.info("Lab: {} upgraded successfully".format(lab['name']))

    # Delete the previous load
    LOG.tc_step("Deleting  {} load... ".format(current_version))
    system_helper.delete_imported_load()
    LOG.tc_step("Delete  previous load version {}".format(current_version))
