from keywords import vm_helper


def test_delete_vm():
    for i in range(20):
        vm_id = vm_helper.boot_vm('del_one', source='image')[1]
        vm_helper.delete_vms(vm_id, stop_first=False, delete_volumes=False)

    # for i in range(10):
    #     vm_id_1 = vm_helper.boot_vm('del_two')[1]
    #     vm_id_2 = vm_helper.boot_vm('del_two')[1]
    #     vm_helper.delete_vms(vms=[vm_id_1, vm_id_2])
