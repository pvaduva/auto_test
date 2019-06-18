import re
import collections

from pytest import fixture, mark, skip

from utils.tis_log import LOG
from consts.stx import VMStatus
from consts.timeout import VMTimeout
from keywords import nova_helper, vm_helper, host_helper, system_helper
from testfixtures.fixture_resources import ResourceCleanup

core_flavor_name = 'flavor_vtpm'
vtpm_base_dir = '/var/lib/nova/instances/{vm_id}/vtpm-{instance_name}/state'
vtpm_file_name = 'tpm2-00.permall'
vtpm_device = '/dev/tpm0'

g_reusable = 0
g_flavors = collections.defaultdict(str)
g_vms = collections.defaultdict(dict)


def reset_vms():
    g_vms.clear()
    g_vms.update(vtpm=None, autorc=None, non_autorc=None)


@fixture(scope='module', autouse=True)
def prepare_vms(request):

    # if not system_helper.is_avs():
    #     skip('CGTS-9999')

    global g_flavors, g_vms

    LOG.info('Prepare VMs for vTPM test')
    reset_vms()

    def clean_up():
        LOG.info('Clean up: delete VMs, volumes, flavors and etc.')

        for vm_type in g_vms:
            if g_vms[vm_type] and 'id' in g_vms[vm_type]:
                vm_id = g_vms[vm_type]['id']
                if vm_id:
                    vm_helper.delete_vms(vm_id)
        nova_helper.delete_flavors(g_flavors.values())
        g_flavors.clear()

    request.addfinalizer(clean_up)


def search_file_on_host(host, where, file_pattern, maxdepth=3):
    with host_helper.ssh_to_host(host) as ssh_client:
        cmd = 'find ' + where + ' -maxdepth ' + str(maxdepth) + ' -name "' + file_pattern + '"'
        LOG.info('searching file using cmd:{}'.format(cmd))
        rc, file = ssh_client.exec_cmd(cmd)
        if rc != 0:
            LOG.info('Failed to find file with pattern:{}, cmd:{}'.format(file_pattern, cmd))
        return rc, file


def verify_vtpm_on_host(vm_id, vm_type='vtpm', host=None):

    if vm_type in ['vtpm', 'autorc', 'non_autorc']:
        LOG.info('Checking files for vTPM on the existing on the host')

        check_host_file_for_vm(vm_id, expecting=True, host=host)

        LOG.info('OK, found the file for vTPM on {}'.format(host if host else 'the active controller'))

    else:
        check_host_file_for_vm(vm_id, expecting=False, host=host)

        LOG.info('OK, no files for vTPM on {}'.format(host if host else 'the active controller'))


def check_host_file_for_vm(vm_id, expecting=True, host=None, fail_ok=True):
    LOG.info('Verify the file for vTPM exists on the hosting node for VM:' + vm_id)
    if host is None:
        host = vm_helper.get_vm_host(vm_id)

    active_controller_name = system_helper.get_active_controller_name()

    instance_name = vm_helper.get_vm_instance_name(vm_id)
    vtpm_file = vtpm_base_dir.format(vm_id=vm_id, instance_name=instance_name) + '/' + vtpm_file_name

    if host != active_controller_name:
        hosting_node = host
    else:
        hosting_node = active_controller_name

    with host_helper.ssh_to_host(hosting_node) as ssh_client:
        if ssh_client.file_exists(vtpm_file):
            LOG.info('OK, found the file for vTPM:{} on host:{}'.format(vtpm_file, host))
            assert expecting is True or fail_ok is True, \
                'FAIL, the files supporting vTPM are NOT found on the {} as expected'.format(host)

            if expecting is True:
                LOG.info('-this is expected')
            else:
                LOG.info('-this is NOT expected')

            return True, expecting

        else:
            LOG.info('Cannot find the file for vTPM:{} on host:{}'.format(vtpm_file, host))
            assert expecting is False or fail_ok is True, \
                'FAIL, the files should be cleared as expected'

            if expecting is False:
                LOG.info('-this is expected')
            else:
                LOG.info('-this is NOT expected')

            return False, expecting


def check_capabilities(ssh_con, after_operation=''):
    LOG.info('checking the capabilities after' + (' ' + str(after_operation) if after_operation else ''))
    get_algorithms = 'tss2_getcapability -cap 0'
    LOG.info('run TSS2 command:' + get_algorithms)
    code, output = ssh_con.exec_cmd(get_algorithms)

    LOG.info('output:' + output)
    msg = 'TPM command returned code:' + str(code) + ', output:' + ', command:' + get_algorithms
    if 0 == code:
        LOG.info(msg)
    else:
        assert False, msg

    return code, output


def vm_op_policy(vm_feature, vm_op, mem_type):
    LOG.info('Check the values after operation:{}, vm features:{}, mem_type:{}'.format(vm_op, vm_feature, mem_type))

    to_be_lost = {
        ('cold-migration', 'transient'),
        ('stop_start', 'transient'),
        ('evacuate', 'transient'),
        ('evacuate', 'persistent', 'vtpm'),  # CGTS-9620
        ('evacuate', 'persistent', 'autorc'),  # CGTS-9620
        ('evacuate', 'non_volatile', 'vtpm'),  # CGTS-9620
        ('evacuate', 'non_volatile', 'autorc'),  # CGTS-9620
        ('resize_to_autorc', 'transient'),
        ('resize_to_non_autorc', 'transient'),
        ('resize_to_non_vtpm', 'non_volatile'),
        ('resize_to_non_vtpm', 'transient'),
        ('resize_to_non_vtpm', 'persistent'),
        ('soft_reboot', 'transient'),
        ('hard_reboot', 'transient'),
        ('reboot_host', 'transient', 'vtpm'),
        ('reboot_host', 'transient', 'autorc'),
        ('reboot_host', 'transient', 'non_autorc'),
        ('reboot_host', 'persistent', 'vtpm'),  # CGTS-9620
        ('reboot_host', 'persistent', 'autorc'),  # CGTS-9620
        ('reboot_host', 'non_volatile', 'vtpm'),  # CGTS-9620
        ('reboot_host', 'non_volatile', 'autorc'),  # CGTS-9620

    }

    if (vm_op, mem_type, vm_feature) in to_be_lost:
        return False

    elif (vm_op, mem_type) in to_be_lost:
        return False

    return True


def list_pcrs(ssh_con, previous_operation=''):
    get_pcrs = 'tss2_getcapability -cap 5'
    LOG.debug('Listing PCRs using cmd:' + get_pcrs + 'after ' + previous_operation)

    code, output = ssh_con.exec_cmd(get_pcrs)

    msg = 'TPM command returned code:' + str(code) + ', output:' + ', command:' + get_pcrs
    if 0 == code:
        LOG.info(msg)
    else:
        assert False, msg

    return code, output


def run_cmd(ssh_con, cmd, cmd_prefix='tss2_', fail_ok=False, output_handle=True, *args, **kwargs):
    cli = cmd_prefix + cmd
    for arg in args:
        if arg:
            cli += ' -' + str(arg)

    for key, value in kwargs.items():
        if value:
            cli += ' -' + str(key)
            if value is not True:
                cli += ' ' + str(value)

    rc, output = ssh_con.exec_cmd(cli)
    if rc == 0:
        LOG.info('OK, successfully ran:' + cli)
        if output_handle:
            handle = output.split()[1]
            LOG.info('-handle: {}'.format(handle))
            return rc, handle

        else:
            return rc, output
    else:
        LOG.info('Failed to run:' + cli + ', but ignore the error as instructed')

        if not fail_ok:
            assert False, 'Failed to run:' + cli

        return rc, output


def create_primary_key(ssh_con, hierarchy='o', pwdp='', pwdpi='', pwdk='', iu='', opu=''):

    options = {'hi': hierarchy, 'pwdp': pwdp, 'pwdpi': pwdpi, 'pwdk': pwdk, 'iu': iu, 'opu': opu}

    return run_cmd(ssh_con, 'createprimary', output_handle=True, **options)[1]


def create_keys(ssh_con, hp='', den=True, st=True, kt=('f', 'p'), opr='private.st.key', opu='public.st.key'):
    if den is True and st is True:
        LOG.warn('Cannot set both "den" and "st"')
        st = False

    cmd = 'create'
    options = {'hp': hp, 'st': st, 'opr': opr, 'opu': opu, 'den': den}

    if isinstance(kt, set) and len(kt) > 0:
        cmd += ' -st ' + ' -st '.join(kt)

    return run_cmd(ssh_con, cmd, output_handle=False, **options)[1]


def create_primary_keys(ssh_con):
    LOG.info('Creating primary key')
    primary_handle = create_primary_key(ssh_con)

    LOG.info('Creating secondary key')
    create_keys(ssh_con, hp=primary_handle)

    LOG.info('OK, primary key hierarchy is successfully created')
    return primary_handle


def generate_hash(ssh_con):
    LOG.info('Generating hash code into a file')

    string_to_hash = 'hello'
    output_file = 'hashed_output.data'
    hash_command = 'tss2_hash -ic "' + string_to_hash + '" -oh ' + output_file

    code, output = ssh_con.exec_cmd(hash_command)

    msg = 'TPM command returned code:' + str(code) + ', output:' + ', command:' + hash_command
    if 0 == code:
        LOG.info(msg)
        # check the output file
        assert ssh_con.file_exists(output_file), 'Failed to generate hash-output file:' + output_file
        LOG.info('OK, the hashed ouput file is successfully generated.')
    else:
        LOG.error('Failed: ' + msg)
        assert False, msg

    return code, output


def generate_random(ssh_con, num_bytes=32):
    LOG.info('Generating random number')

    get_random_number = 'tss2_getrandom -by ' + str(num_bytes)
    code, output = ssh_con.exec_cmd(get_random_number)

    msg = 'TPM command returned code:' + str(code) + ', output:' + ', command:' + get_random_number
    if 0 == code:
        LOG.info(msg)
        numbers = []
        for line in output.splitlines()[1:]:
            numbers += line.split()

        assert num_bytes == len(numbers), \
            'Requesting {} random numbers, but got {} numbers instead'.format(num_bytes, len(numbers))

        LOG.info('OK, random numbers got:{}'.format(numbers))
    else:
        assert False, msg

    return code, output


def delete_handle(ssh_con, handle):
    LOG.info('Deleting handle:' + str(handle))

    cli = 'flushcontext -ha ' + str(handle)
    run_cmd(ssh_con, cli, output_handle=False)
    LOG.info('-OK, successfully deleted handle:' + str(handle))


def clean_up_tpm(ssh_con, handles=None):
    LOG.info('clean up files')
    rm_files = 'rm -rf h80[0]* hp80[0]*'
    ssh_con.exec_cmd(rm_files, fail_ok=True)
    if handles:
        to_delete = []
        if isinstance(handles, list) or isinstance(handles, tuple):
            to_delete = [h for h in handles if h]
        for h in to_delete:
            delete_handle(ssh_con, h)


def get_volatile_content(ssh_con, fail_ok=False):
    cmd = 'getcapability -cap 1 -pr 0x80000000'
    rc, output = run_cmd(ssh_con, cmd, output_handle=False, fail_ok=fail_ok)

    if rc == 0:
        handles = []
        if output:
            for line in output.splitlines():
                m = re.match('^\s*([\d]{8})\s*$', line)
                if m and len(m.groups()) == 1:
                    handles.append(m.group(1))
            return rc, handles
    else:
        if fail_ok:
            return rc, output
        else:
            assert False, 'Failed to run cmd:' + cmd

    return rc, []


def create_nv_values(ssh_con, size=32, in_file=None):
    LOG.info('create non_volatile contents')
    if in_file is not None and ssh_con.file_exists(in_file):
        LOG.info('from file:' + in_file)
        in_file_name = in_file
    else:
        LOG.info('No input content')
        in_file_name = "nv_data.txt"
        ssh_con.exec_cmd('echo "test data for non_volatile memory" > ' + in_file_name)
        ssh_con.exec_cmd('truncate -s ' + str(size) + ' ' + in_file_name)
        assert ssh_con.file_exists(in_file_name), 'Failed to create a test file:' + in_file_name

    handle = '01200000'
    cli = 'nvdefinespace -ha ' + handle + ' -hi o -sz ' + str(size)
    output = run_cmd(ssh_con, cli, output_handle=False)[1]
    LOG.info('OK, got:' + output)

    output = run_cmd(ssh_con, 'nvwrite -ha {} -if {}'.format(handle, in_file_name), output_handle=False)[1]
    LOG.info('nv content created:' + output)

    return handle, 32, in_file_name


def check_nv_values(ssh_con, handle, size=32, expecting=True, fail_ok=False):
    LOG.info('check if nv content exists')

    output = ''
    try:
        rc, output = run_cmd(ssh_con, 'nvread -ha {} -sz {}'.format(handle, size), output_handle=False, fail_ok=fail_ok)
    except Exception as e:
        LOG.info('Caught exception:{} when run cmd: "nvread -ha..."'.format(e))
        rc = 1

    if rc == 0:
        if expecting is True:
            LOG.info('Found the non_volatile contents:' + output + ' as epxected')
            return True, output, handle
        else:
            LOG.info('Not expecting but find non-volatile contents for:{}'.format(handle))
            if fail_ok:
                return False, output, handle
            else:
                assert False, 'Not expecting but find non-volatile contents for:{}'.format(handle)
    else:
        if expecting is False:
            LOG.info('OK, did not find the NV content, this is expected.')
            return True, output, handle
        else:
            LOG.warn('Did not find the NV content but expecting.')
            if fail_ok:
                return False, output, handle
            else:
                assert False, 'Expecting but failed to find non_volatile contents for handle:' + str(handle)


def create_persistent_values(ssh_con, handle, to_handle=None, fail_ok=False):
    LOG.info('Write to PERSISTENT memory')
    persistent_handle = '0x81000000' if to_handle is None else to_handle
    cli = 'evictcontrol'
    options = {'hi': 'o', 'ho': handle, 'hp': persistent_handle}
    output = run_cmd(ssh_con, cli, fail_ok=fail_ok, output_handle=False,  **options)[1]
    LOG.info('OK, created persistent value:' + persistent_handle + ', output:' + output)
    return persistent_handle


def check_persistent_values(ssh_con, handle, expecting=True, fail_ok=False):
    LOG.info('Check if the value still existing for handle:{}'.format(handle))

    cli = 'getcapability -cap 1 -pr ' + str(handle)

    output = ''
    try:
        output = run_cmd(ssh_con, cli, output_handle=False, fail_ok=fail_ok)[1]
    except Exception as e:
        LOG.warn('Caught exception: {}'.format(e))

    if str(handle) in output or str(handle)[2:] in output:
        if expecting is True:
            LOG.info('OK, found the value in persistent memory, handle:' + handle + ' as expected')
            return True, handle, output
        else:
            LOG.warn('Not expecting but got value for handle:{}, results:{}'.format(handle, output))
            if fail_ok:
                return False, output, handle
            else:
                assert False, 'Not-expecting but find the persistent contents:' + str(handle)

    else:
        if expecting is True:
            LOG.warn('Expecting but could not find the persistent values')
            if fail_ok:
                return False, output, handle
            assert False, 'Could not find the persistent values, while expecting them'

        else:
            LOG.info('OK, as expected, no value in persistent memory, handle:' + handle)
            return True, output, handle


def create_testing_key(ssh_con, handle=None):
    LOG.info('Creating keys')

    if handle is not None:
        return handle

    else:
        handles = get_volatile_content(ssh_con)[1]

        if not handles:
            LOG.info('Create a primary key')
            primary_handle = create_primary_key(ssh_con)
            LOG.info('OK, successuflly created primary key: ' + str(primary_handle))

            return primary_handle

    return handles[-1]


def check_transient_values(ssh_con, handles=None, expecting=True, fail_ok=False):
    LOG.info('Check if the values stored in volatile memory existing or not, expecting: {}'.format(expecting))

    if handles:
        if isinstance(handles, list) or isinstance(handles, tuple):
            to_check = [h for h in handles if h]
        else:
            to_check = [handles]
    else:
        LOG.info('check if any values in volatile memory')
        to_check = []

    rc, values = get_volatile_content(ssh_con, fail_ok=fail_ok)

    if rc == 0 and values == to_check:
        if expecting is True:
            LOG.info('OK, found transient contents as expected')
            return True, values, handles
        else:
            LOG.warn('Not expecting but find values for handles:{}, vaules:{}'.format(handles, values))
            if fail_ok:
                return False, values, handles
            assert False, 'Failed, expecting nothing in transient memory, but got {}'.format(values)

    else:
        if expecting is False:
            LOG.info('OK, as expected, no transient contents found')
            return True, values, handles
        else:
            LOG.warn('Expecting but failed to find values for handles:{}'.format(handles))
            if fail_ok:
                return True, values, handles
            else:
                assert False, 'Failed to find expected contents:{}'.format(to_check)


def get_flavor_id(vm_type, flavor_type):
    global g_flavors
    return create_flavor(vm_type, flavor_type)


def create_flavor(vm_type, flavor_type=None, name=core_flavor_name):
    global g_flavors

    extra_specs = {}

    if 'non_vtpm' in vm_type or (flavor_type and 'non_vtpm' in flavor_type):
        name += '_nonvtpm'
        extra_specs['sw:wrs:vtpm'] = 'false'
    else:
        extra_specs['sw:wrs:vtpm'] = 'true'

    if 'non_autorc' in vm_type or (flavor_type and 'non_autorc' in flavor_type):
        name += '_nonrc'
        extra_specs['sw:wrs:auto_recovery'] = 'false'

    elif 'autorc' in vm_type or (flavor_type and 'autorc' in flavor_type):
        name += '_autorc'
        extra_specs['sw:wrs:auto_recovery'] = 'true'

    flavor_id = nova_helper.create_flavor(name=name)[1]
    nova_helper.set_flavor(flavor_id, **extra_specs)

    if flavor_type is not None:
        g_flavors[flavor_type] = flavor_id
    else:
        g_flavors[vm_type] = flavor_id

    return flavor_id


def create_flavors():
    global g_flavors

    types = ['vtpm', 'autorc', 'autorc2', 'non_autorc', 'non_autorc2', 'non_vtpm']
    for vm_type in types:
        create_flavor(vm_type)

    return list(g_flavors.values())


def create_vm_values_for_type(vm_type, flavor=None):
    global g_flavors, g_vms

    LOG.info('Creating VM for vTPM using flavor:' + g_flavors[vm_type])

    flavor = flavor if flavor is not None else g_flavors[vm_type]
    code, vm_id, msg = vm_helper.boot_vm(name='vm-{}'.format(vm_type), flavor=flavor, cleanup='function')

    vm_values = {'id': vm_id}
    g_vms[vm_type] = vm_values

    vm_helper.wait_for_vm_pingable_from_natbox(vm_id)
    with vm_helper.ssh_to_vm_from_natbox(vm_values['id']) as ssh_to_vm:
        vm_values['values'] = create_values(ssh_to_vm, vm_type)

    return vm_id


def create_values(ssh_con, vm_type):
    global g_vms

    all_types = ['transient', 'non_volatile', 'persistent']

    values = {}
    for value_type in all_types:
        values[value_type] = create_value(ssh_con, value_type)

    return values


def create_value(ssh_con, value_type='transient'):
    global g_vms, g_flavors

    LOG.info('Create values for types:{}'.format(value_type))

    try:
        if g_vms[value_type] and g_vms[value_type]['values']:
            LOG.info('The values for the vm-type are already created, vm_type:{}, values:{}'.format(
                value_type, g_vms[value_type]['values']))
            return g_vms[value_type]['values']

    except (TypeError, KeyError):
        pass

    key = ''
    if 'transient' in value_type:
        LOG.info('Creating values for types:{}'.format(value_type))
        LOG.info('-Creating transient values')
        key = create_testing_key(ssh_con)
        LOG.info('-OK, successfully created transient values:{}'.format(key))

        return key

    if 'non_volatile' in value_type:
        LOG.info('-Creating non_volatile values')
        nv = create_nv_values(ssh_con)[0]
        LOG.info('-OK, successfully created non_volatile value:{}'.format(nv))
        return nv

    if 'persistent' in value_type:
        if not key:
            LOG.info('-Creating transient values')

            key = create_testing_key(ssh_con)
            LOG.info('-OK, successfully created transient values:{}'.format(key))

        LOG.info('-Create persistent values')
        persistent = create_persistent_values(ssh_con, key)
        LOG.info('-OK, successfully created persistent value:{}'.format(persistent))
        return persistent

    return ''


def resize_to(vm_type, vm_id):
    if vm_type == 'autorc':
        flavor = g_flavors['vtpm']
    elif vm_type == 'non_autorc':
        flavor = g_flavors['autorc']
    elif vm_type == 'vtpm':
        flavor = g_flavors['autorc']
    else:
        flavor = g_flavors['vtpm']

    LOG.info('-resize to another flavor with vTPM/auto-recovery enabled')
    vm_helper.resize_vm(vm_id, flavor_id=flavor)


def rescue_vm(vm_type, vm_id):
    if 'non_autorc' in vm_type:
        vm_helper.wait_for_vm_status(vm_id, status=VMStatus.ERROR, timeout=VMTimeout.AUTO_RECOVERY)

        LOG.warn('VM got into ERROR status as expected')
        LOG.warn('Attempting to rescure the VM:{}'.format(vm_id))
        vm_helper.stop_vms(vm_id)
        vm_helper.start_vms(vm_id)


def reboot_hosting_node(vm_type, vm_id, force_reboot=False):
    host = vm_helper.get_vm_host(vm_id)

    host_helper.reboot_hosts(host, force_reboot=force_reboot)
    rescue_vm(vm_type, vm_id)


def lock_unlock_hosting_node(vm_type, vm_id, force_lock=False):
    host = vm_helper.get_vm_host(vm_id)
    host_helper.lock_host(host, force=force_lock)
    host_helper.unlock_host(host)

    rescue_vm(vm_type, vm_id)


def perform_vm_operation(vm_type, vm_id, op='live_migration', extra_specs='vtpm'):
    LOG.info('Perform action:{} to the VM, extra specs:{}'.format(op, extra_specs))

    op_table = {
        'live_migration': lambda x, y: vm_helper.live_migrate_vm(y),
        'cold_migration': lambda x, y: vm_helper.cold_migrate_vm(y),
        'stop_start': lambda x, y: (vm_helper.stop_vms(y), vm_helper.start_vms(y)),
        'suspend_resume': lambda x, y: (vm_helper.suspend_vm(y), vm_helper.resume_vm(y)),
        'pause_unpause': lambda x, y: (vm_helper.pause_vm(y), vm_helper.unpause_vm(y)),
        'reboot_host': lambda x, y: reboot_hosting_node(x, y, force_reboot=False),
        'soft_reboot': lambda x, y: vm_helper.reboot_vm(y, hard=False),
        'hard_reboot': lambda x, y: vm_helper.reboot_vm(y, hard=True),
        'lock_unlock': lambda x, y: lock_unlock_hosting_node(x, y, force_lock=False),
        'evacuate': lambda x, y: reboot_hosting_node(x, y, force_reboot=True),
    }

    if op in op_table:
        LOG.info('Perform action: {}'.format(op))
        op_table[op](vm_type, vm_id)

        return True

    elif op == 'resize_to_autorc':
        if vm_type == 'autorc':
            LOG.info('resize from AUTO-RECOVERY to another AUTO-RECOVER flavor')

        to_flavor_id = get_flavor_id(vm_type, 'autorc2')

        LOG.info('TODO: {}, m_type={}, to_flavor_id={}'.format(to_flavor_id, vm_type, to_flavor_id))

        vm_helper.resize_vm(vm_id, to_flavor_id)

    elif op == 'resize_to_non_autorc':
        LOG.info('perform {} on type:{}, id:{}'.format(op, vm_type, vm_id))
        if vm_type == 'non_autorc2':
            LOG.warn('resize from AUTO-RECOVERY to another AUTO-RECOVER flavor')

        to_flavor_id = get_flavor_id(vm_type, 'non_autorc2')
        vm_helper.resize_vm(vm_id, to_flavor_id)

    elif op == 'resize_to_non_vtpm':
        LOG.info('perform {} on type:{}, id:{}'.format(op, vm_type, vm_id))

        to_flavor_id = get_flavor_id(vm_type, 'non_vtpm')

        vm_helper.resize_vm(vm_id, to_flavor_id)

    else:
        LOG.fatal('Unsupported action: {}'.format(op))
        return False


def get_vm_id(vm_type, reuse=True):
    global g_vms, g_flavors

    LOG.info('Make sure the VM for the specified type exists, create if it does not')

    if reuse and g_vms[vm_type] and 'id' in g_vms[vm_type]:
        vm_id = g_vms[vm_type]['id']
        LOG.info('VM exists for type:{}, vm_id:{}'.format(vm_type, vm_id))

        if reuse and vm_helper.get_vm_status(vm_id=vm_id) == VMStatus.ACTIVE:
            return vm_id

    LOG.info('not reusing...')
    vm_helper.delete_vms()
    reset_vms()

    if not g_flavors[vm_type]:
        create_flavor(vm_type)

    vm_id = create_vm_values_for_type(vm_type)

    return vm_id


def reuse_existing_vms(vm_operation, extra_specs):
    global g_reusable

    if not g_reusable:
        return False

    if 'reboot_host' == vm_operation or 'evacuate' in vm_operation or 'non_autorc' in extra_specs or \
            'non_vtpm' in extra_specs:
        return False

    return True


# US129306
@mark.parametrize(('vm_operation', 'extra_specs'), [
    ('create', 'vtpm'),
    ('create', 'autorc'),
    ('create', 'non_autorc'),
    ('live_migration', 'vtpm'),
    ('live_migration', 'autorc'),
    ('live_migration', 'non_autorc'),
    #
    ('cold_migration', 'vtpm'),
    ('cold_migration', 'autorc'),
    ('cold_migration', 'non_autorc'),
    #
    ('stop_start', 'vtpm'),
    ('stop_start', 'autorc'),
    ('stop_start', 'non_autorc'),
    #
    ('suspend_resume', 'vtpm'),
    ('suspend_resume', 'autorc'),
    ('suspend_resume', 'non_autorc'),

    ('pause_unpause', 'vtpm'),
    ('pause_unpause', 'autorc'),
    ('pause_unpause', 'non_autorc'),
    #
    ('pause_unpause', 'vtpm'),

    ('soft_reboot', 'vtpm,'),
    ('soft_reboot', 'autorc'),
    ('soft_reboot', 'non_autorc'),
    #
    ('hard_reboot', 'vtpm,'),
    ('hard_reboot', 'autorc'),
    ('hard_reboot', 'non_autorc'),

    ('lock_unlock', 'vtpm'),

    ('reboot_host', 'vtpm'),
    ('reboot_host', 'autorc'),  # fail
    ('reboot_host', 'non_autorc'),

    ('evacuate', 'vtpm'),
    ('evacuate', 'autorc'),
    ('evacuate', 'non_autorc'),
    #
    ('resize_to_autorc', 'vtpm'),
    ('resize_to_autorc', 'non_autorc'),
    ('resize_to_non_autorc', 'autorc'),
    ('resize_to_non_autorc', 'vtpm'),

    ('resize_to_non_vtpm', 'vtpm'),
])
def _test_vtpm(vm_operation, extra_specs):
    global g_vms, g_reusable

    LOG.tc_step('Verify vTPM is functioning on VMs right after they are: {}'.format(vm_operation))
    LOG.info('Will perform action:{}'.format(vm_operation))

    number_hypervisor = len(host_helper.get_up_hypervisors())
    if number_hypervisor < 2 and 'migrate' in vm_operation:
        skip('Not enough hypervisors available for testing')

    vm_types = [vm_type for vm_type in extra_specs.split(',') if vm_type in g_vms]

    for vm_type in vm_types:
        reuse = reuse_existing_vms(vm_operation, extra_specs)

        vm_id = get_vm_id(vm_type, reuse=reuse)
        LOG.info('-check vTPM supports on hosting node for VM:' + vm_id + ', vm-type:' + vm_type)

        verify_vtpm_on_host(vm_id, host=None)
        LOG.info('-OK, passed checking on hosting node for VM:' + vm_id + ', vm-type:' + vm_type)

        if vm_operation == 'create':
            with vm_helper.ssh_to_vm_from_natbox(vm_id) as ssh_to_vm:
                LOG.info('Create all types of contents: volatile, non_volatile and persistent')
                create_values(ssh_to_vm, vm_type)

        values = g_vms[vm_type]['values']
        LOG.info('Running test on VM:{}, type:{}, values:{}'.format(vm_id, vm_type, values))

        # fail_ok = (vm_operation == 'resize_to_non_vtpm')
        fail_ok = True
        perform_vm_operation(vm_type, vm_id, op=vm_operation, extra_specs=extra_specs)
        ping_timeout = VMTimeout.DHCP_RETRY if vm_operation in ('reboot_host', 'evacuate') else VMTimeout.PING_VM
        vm_helper.wait_for_vm_pingable_from_natbox(vm_id, timeout=ping_timeout)

        with vm_helper.ssh_to_vm_from_natbox(vm_id, timeout=(int(VMTimeout.SSH_LOGIN * 1.3))) as ssh_to_vm:
            LOG.info('After VM operation:{}, check all types of contents'.format(vm_operation))

            passed = []
            if 'persistent' in values:
                if check_persistent_values(
                        ssh_to_vm, values['persistent'],
                        expecting=vm_op_policy(vm_type, vm_operation, 'persistent'),
                        fail_ok=fail_ok)[0]:
                    passed.append('persistent')

            if 'non_volatile' in values:
                if check_nv_values(
                        ssh_to_vm, values['non_volatile'],
                        expecting=vm_op_policy(vm_type, vm_operation, 'non_volatile'),
                        fail_ok=fail_ok)[0]:
                    passed.append('non_volatile')

            if 'transient' in values:
                if check_transient_values(
                        ssh_to_vm,
                        handles=values['transient'],
                        expecting=vm_op_policy(vm_type, vm_operation, 'transient'),
                        fail_ok=fail_ok)[0]:
                    passed.append('transient')

            if len(passed) < 3:
                all_checks = ['persistent', 'non_volatile', 'transient']
                message = 'Failed in verify {} contents'.format(', '.join(set(all_checks) - set(passed)))
                assert False, message

            if 'reboot_host' == vm_operation \
                    or 'evacuate' in vm_operation\
                    or 'resize_to_non_vtpm' in vm_operation\
                    or 'non_autorc' in extra_specs \
                    or 'non_vtpm' in extra_specs:
                g_reusable = False
            else:
                g_reusable = True
