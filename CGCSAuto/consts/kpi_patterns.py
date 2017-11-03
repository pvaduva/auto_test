class DRBDSync:
    LOG_PATH = '/var/log/kern.log'
    GREP_PATTHERN = 'Resync done'
    PYTHON_PATTERN = 'Resync done .* (\d+) K\/sec'


class VMRecovery:
    LOG_PATH = '/var/log/nova/nova-compute.log'
    START = '{}.* VM Crashed.*Lifecycle Event'
    END = '{}.* VM Started.*Lifecycle Event'


class ConfigController:
    LOG_PATH = '/var/log/bash.log'
    START = 'localhost .*sudo -S config_controller'
    END = 'controller-0'
