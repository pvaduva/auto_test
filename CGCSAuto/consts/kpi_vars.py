KPI_DATE_FORMAT = '%Y-%m-%d %T'


class DRBDSync:
    NAME = 'drbd_sync(K/s)'
    LOG_PATH = '/var/log/kern.log'
    GREP_PATTERN = 'Resync done'
    PYTHON_PATTERN = 'Resync done .* (\d+) K\/sec'
    UNIT = 'Rate(K/s)'


class VMRecoveryNova:
    NAME = 'vm_recovery'
    LOG_PATH = '/var/log/nova/nova-compute.log'
    START = '{}.* VM Crashed.*Lifecycle Event'
    END = '{}.* VM Started.*Lifecycle Event'


class VMRecoveryNetworking:
    NAME = 'vm_recovery_networking'


class ConfigController:
    NAME = 'config_controller'
    LOG_PATH = '/var/log/bash.log'
    START = 'localhost .*sudo .*config_controller'
    END = 'controller-0'


class SystemInstall:
    NAME = 'system_install'
    LOG_PATH = '/var/log/bash.log'
    START = 'setting system clock to'
    START_PATH = '/var/log/anaconda/journal.log'
    END = '/etc/build.info'


class NodeInstall:
    NAME = '{}_install'
    LOG_PATH = '/var/log/mtclogd.log'
    START = 'setting system clock to'
    START_PATH = '/var/log/anaconda/journal.log'
    END = 'initial_config_complete'


class HostLock:
    NAME = '{}_lock'
    WITH_VM = 'host_lock_with_vms_{}'
    LOG_PATH = '/var/log/fm-event.log'
    END = '200.001.*{} was administratively locked to take it out-of-service.*set'
    START = 'system.*host-lock.*{}'
    START_PATH = '/var/log/bash.log'


class HostUnlock:
    NAME = '{}_unlock'
    LOG_PATH = '/var/log/fm-event.log'
    END = {
        'controller': '401.001.*Service group web-services state change from go-active to active on host {}.*msg',
        'storage': "200.022.*{} is now 'enabled'.*msg",
        'compute': '275.001.* {} hypervisor is now unlocked-enabled.*msg',
    }
    START = 'system.*host-unlock.*{}'
    START_PATH = '/var/log/bash.log'


class LabSetup:
    NAME = 'lab_setup'
    LOG_PATH = '/var/log/bash.log'
    START = 'lab_setup.sh'
    END = '.heat_resources'


class HeatStacks:
    NAME = 'heat_stacks'
    LOG_PATH = '/var/log/bash.log'
    START = 'launch_stacks.sh lab_setup.conf'
    END = 'source /etc/nova/openrc'


class VolCreate:
    NAME = 'volume_creation'
    START = 'cinder .*create .*20g'
    LOG_PATH = '/var/log/bash.log'


class ImageDownload:
    NAME = 'image_download(MB/s)'
    LOG_PATH = '/var/log/cinder/cinder-volume.log'
    GREP_PATTERN = 'Image download .* at'
    PYTHON_PATTERN = 'Image download .* at (.*) MB/s'
    UNIT = 'Rate(MB/s)'


class ImageConversion:
    NAME = 'image_conversion(MB/s)'
    LOG_PATH = '/var/log/cinder/cinder-volume.log'
    GREP_PATTERN = 'Converted .* at'
    PYTHON_PATTERN = 'Converted .* image at (.*) MB/s'
    UNIT = 'Rate(MB/s)'


class VmStartup:
    NAME = 'vm_startup_{}'
    LOG_PATH = '/var/log/fm-event.log'
    START = 'Instance .* owned by .* has been created.*{}'
    END = 'Instance .* is enabled on host .*{}'


class Swact:
    NAME = 'swact_controlled'
    START_PATH = '/var/log/bash.log'
    START = 'system .*host-swact'
    LOG_PATH = '/var/log/sm.log'
    END = 'Swact has completed successfully'


class SwactUncontrolled:
    NAME = 'swact_uncontrolled'
    START_PATH = '/var/log/bash.log'
    START = 'sudo reboot -f'
    LOG_PATH = '/var/log/sm.log'
    END = 'Swact has completed successfully'


class LiveMigrate:
    NAME = 'live_migrate_{}'


class ColdMigrate:
    NAME = 'cold_migrate_{}'


class Rebuild:
    NAME = 'rebuild_{}'


class Evacuate:
    NAME = 'evacuate_{}_{}_router'


class Idle:
    NAME_CPU = 'idle_platform_cpu'
    NAME_MEM = 'idle_mem_usage'