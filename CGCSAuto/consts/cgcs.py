# output of date. such as: Tue Mar  1 18:20:29 UTC 2016
DATE_OUTPUT = r'[01]\d:[0-5]\d:[0-5]\d\s[A-Z]{3}\s\d{4}$'

# such as 192.168.11.6
MGMT_IP = r'mgmt-net\d?=.*(192.168\.\d{1,3}\.\d{1,3})'

# such as in string '5 packets transmitted, 0 received, 100% packet loss, time 4031ms', number 100 will be found
PING_LOSS_RATE = r'\, (\d{1,3})\% packet loss\,'

# Matches 8-4-4-4-12 hexadecimal digits. Lower case only
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

# Match name and uuid. Such as: 'cgcs-guest (a764c205-eb82-4f18-bda6-6c8434223eb5)'
NAME_UUID = r'(.*) \((' + UUID + r')\)'

# Message to indicate boot from volume from nova show
BOOT_FROM_VOLUME = 'Attempt to boot from volume - no image supplied'


class SystemType:
    CPE = 'CPE'
    STANDARD = 'Standard'


class HostStorageBacking:
    LOCAL_LVM = 'local_storage_lvm_hosts'
    LOCAL_IMAGE = 'local_storage_image_hosts'
    REMOTE = 'remote_storage_hosts'


class VMStatus:
    ACTIVE = 'ACTIVE'
    BUILD = 'BUILD'
    VERIFY_RESIZE = 'VERIFY_RESIZE'
    RESIZE = 'RESIZE'
    ERROR = 'ERROR'
    SUSPENDED = 'SUSPENDED'
    PAUSED = 'PAUSED'
    NO_STATE = 'NO STATE'


class HostAdminState:
    UNLOCKED = 'unlocked'
    LOCKED = 'locked'


class HostOperationalState:
    ENABLED = 'enabled'
    DISABLED = 'disabled'


class HostAavailabilityState:
    DEGRADED = 'degraded'
    OFFLINE = 'offline'
    ONLINE = 'online'
    AVAILABLE = 'available'
    FAILED = 'failed'


class HostTask:
    BOOTING = 'Booting'
    REBOOTING = 'Rebooting'


class Prompt:
    CONTROLLER_0 = '.*controller\-0\:~\$ '
    CONTROLLER_1 = '.*controller\-1\:~\$ '
    ADMIN_PROMPT = '\[wrsroot@controller\-[01] ~\(keystone_admin\)\]\$ '
    COMPUTE_PROMPT = '.*compute\-([0-9]){1,}\:~\$'
    PASSWORD_PROMPT = '.*assword\:.*'
    ADD_HOST = '.*\(yes/no\).*'


class NovaCLIOutput:
    VM_DELETE_REJECTED_NOT_EXIST = "No server with a name or ID of '(.*)' exists."
    VM_DELETE_ACCEPTED = "Request to delete server () has been accepted."


class FlavorSpec:
    VCPU_MODEL = 'hw:cpu_model'
    STORAGE_BACKING = 'aggregate_instance_extra_specs:localstorage'
    NUMA_0 = 'hw:numa_node.0'
    NUMA_NODES = 'hw:numa_nodes'
