CLI_TIMEOUT = 10


class HostTimeout:
    ONLINE_AFTER_LOCK = 180
    COMPUTE_UNLOCK = 840
    CONTROLLER_UNLOCK = 1360
    REBOOT = 1360
    SWACT = 140


class VMTimeout:
    STATUS_CHANGE = 120
    STATUS_VERIFY_RESIZE = 30
    LIVE_MIGRATE_COMPLETE = 60
    COLD_MIGRATE_CONFIRM = 120
    BOOT_VM = 60


class VolumeTimeout:
    STATUS_CHANGE = 720
