from keywords import vm_helper, cinder_helper


def test_delete_vms_and_vols():
    """
    Delete vms and volumes on the system.
    Usage: normally run before a formal test session (sanity, regression, etc) starts to ensure a clean system

    """
    vm_helper.delete_vms()
    cinder_helper.delete_volumes()
