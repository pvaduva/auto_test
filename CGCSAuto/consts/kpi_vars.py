KPI_DATE_FORMAT = '%Y-%m-%d %T'


class DRBDSync:
    NAME = 'drbd_sync(K/s)'
    LOG_PATH = '/var/log/kern.log'
    GREP_PATTERN = 'Resync done'
    PYTHON_PATTERN = 'Resync done .* (\d+) K\/sec'


class VMRecovery:
    NAME = 'vm_recovery'
    LOG_PATH = '/var/log/nova/nova-compute.log'
    START = '{}.* VM Crashed.*Lifecycle Event'
    END = '{}.* VM Started.*Lifecycle Event'


class ConfigController:
    NAME = 'config_controller'
    LOG_PATH = '/var/log/bash.log'
    START = 'localhost .*sudo -S config_controller'
    END = 'controller-0'


class HostLock:
    NAME = '{}_lock'
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


class ImageConversion:
    NAME = 'image_conversion((MB/s))'
    LOG_PATH = '/var/log/cinder/cinder-volume.log'
    GREP_PATTERN = 'Converted .* at'
    PYTHON_PATTERN = 'Converted .* image at (.*) MB/s'


class VmStartup:
    NAME = 'vm_startup'
    START = 'Instance {}.* owned by .* has been created'
