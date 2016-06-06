# output of date. such as: Tue Mar  1 18:20:29 UTC 2016
DATE_OUTPUT = r'[0-2]\d:[0-5]\d:[0-5]\d\s[A-Z]{3}\s\d{4}$'

EXT_IP = '8.8.8.8'

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


IMAGE_DIR = '/home/wrsroot/images'

DNS_NAMESERVERS = ["147.11.57.133", "128.224.144.130", "147.11.57.128"]


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
    HARD_REBOOT = 'HARD REBOOT'
    SOFT_REBOOT = 'REBOOT'
    STOPPED = "SHUTOFF"


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
    CONTROLLER_PROMPT = '.*controller\-[01]\:~\$ '
    ADMIN_PROMPT = '\[wrsroot@controller\-[01] ~\(keystone_admin\)\]\$ '
    COMPUTE_PROMPT = '.*compute\-([0-9]){1,}\:~\$'
    STORAGE_PROMPT = '.*storage\-([0-9]){1,}\:~\$'
    PASSWORD_PROMPT = '.*assword\:.*'
    ADD_HOST = '.*\(yes/no\).*'
    ROOT_PROMPT = '.*root@.*'


class NovaCLIOutput:
    VM_ACTION_ACCEPTED = "Request to {} server (.*) has been accepted."
    VM_START_ACCEPTED = "Request to start server (.*) has been accepted."
    VM_STOP_ACCEPTED = "Request to stop server (.*) has been accepted."
    VM_DELETE_REJECTED_NOT_EXIST = "No server with a name or ID of '(.*)' exists."
    VM_DELETE_ACCEPTED = "Request to delete server (.*) has been accepted."
    VM_BOOT_REJECT_MEM_PAGE_SIZE_FORBIDDEN = "Page size .* forbidden against .*"
    SRV_GRP_DEL_REJ_NOT_EXIST = "Delete for server group (.*) failed"
    SRV_GRP_DEL_SUCC = "Server group (.*) has been successfully deleted."


class FlavorSpec:
    CPU_POLICY = 'hw:cpu_policy'
    VCPU_MODEL = 'hw:cpu_model'
    SHARED_VCPU = 'hw:wrs:shared_vcpu'
    STORAGE_BACKING = 'aggregate_instance_extra_specs:storage'
    # LOCAL_STORAGE = 'aggregate_instance_extra_specs:localstorage'
    NUMA_NODES = 'hw:numa_nodes'
    NUMA_0 = 'hw:numa_node.0'
    NUMA_1 = 'hw:numa_node.1'
    MEM_PAGE_SIZE = 'hw:mem_page_size'
    AUTO_RECOVERY = 'sw:wrs:auto_recovery'
    GUEST_HEARTBEAT = 'sw:wrs:guest:heartbeat'
    VCPU_SCHEDULER = 'hw:wrs:vcpu:scheduler'
    MIN_VCPUS = "hw:wrs:min_vcpus"
    SRV_GRP_MSG = "sw:wrs:srv_grp_messaging"
    NIC_ISOLATION = "hw:wrs:nic_isolation"


class ImageMetadata:
    MEM_PAGE_SIZE = 'hw_mem_page_size'
    AUTO_RECOVERRY = 'sw_wrs_auto_recovery'
    VIF_MODEL = 'hw_vif_model'


class ServerGroupMetadata:
    BEST_EFFORT = "wrs-sg:best_effort"
    GROUP_SIZE = "wrs-sg:group_size"


class InstanceTopology:
    NODE = 'node:(\d),'
    PGSIZE = 'pgsize:(\d{1,3})M,'
    VCPUS = 'vcpus:(\d{1,2}),'
    PCPUS = 'pcpus:(.*),\s'     # find a string separated by ',' if multiple numa nodes
    CPU_POLICY = 'pol:(.*),'


class RouterStatus:
    ACTIVE = 'ACTIVE'
    DOWN = 'DOWN'


class EventLogID:
    HEARTBEAT_ENABLED = '700.211'
    HEARTBEAT_DISABLED = '700.015'
    HEARTBEAT_CHECK_FAILED = '700.215'
    SOFT_REBOOT_BY_VM = '700.181'
    REBOOT_VM_INPROGRESS = '700.182'
    REBOOT_VM_COMPLETE = '700.186'
    GUEST_HEALTH_CHECK_FAILED = '700.215'
    VM_DELETING = '700.110'
    VM_DELETED = '700.114'
    VM_CREATED = '700.108'
    VM_FAILED = '700.001'
