CLI_TIMEOUT = 10


class HostTimeout:
    ONLINE_AFTER_LOCK = 600
    COMPUTE_UNLOCK = 840
    CONTROLLER_UNLOCK = 1360
    REBOOT = 1360
    SWACT = 140
    LOCK = 720


class VMTimeout:
    STATUS_CHANGE = 120
    STATUS_VERIFY_RESIZE = 30
    LIVE_MIGRATE_COMPLETE = 120
    COLD_MIGRATE_CONFIRM = 120
    BOOT_VM = 180
    DELETE = 180
    VOL_ATTACH = 60
    SSH_LOGIN = 20
    AUTO_RECOVERY = 600


class VolumeTimeout:
    STATUS_CHANGE = 720
    DELETE = 60


class SysInvTimeout:
    RETENTION_PERIOD_SAVED = 30
    RETENTION_PERIOD_MDOIFY = 60
    DNS_SERVERS_SAVED = 30
    DNS_MODIFY = 60


class CMDTimeout:
    HOST_CPU_MODIFY = 30


class ImageTimeout:
    CREATE = 600
    STATUS_CHANGE = 30
    DELETE = 120


class EventLogTimeout:
    HEARTBEAT_ESTABLISH = 120
    HEALTH_CHECK_FAIL = 30
