# output of date. such as: Tue Mar  1 18:20:29 UTC 2016
DATE_OUTPUT = r'[0-2]\d:[0-5]\d:[0-5]\d\s[A-Z]{3}\s\d{4}$'

EXT_IP = '8.8.8.8'

# such as in string '5 packets transmitted, 0 received, 100% packet loss, time 4031ms', number 100 will be found
PING_LOSS_RATE = r'\, (\d{1,3})\% packet loss\,'

# Matches 8-4-4-4-12 hexadecimal digits. Lower case only
UUID = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'

# Match name and uuid. Such as: 'cgcs-guest (a764c205-eb82-4f18-bda6-6c8434223eb5)'
NAME_UUID = r'(.*) \((' + UUID + r')\)'

# Message to indicate boot from volume from nova show
BOOT_FROM_VOLUME = 'Attempt to boot from volume - no image supplied'

DNS_NAMESERVERS = ["147.11.57.133", "128.224.144.130", "147.11.57.128"]

# Heat template path
HEAT_PATH = 'heat/hot/simple/'
HEAT_SCENARIO_PATH = 'heat/hot/scenarios/'
MELLANOX_DEVICE = 'MT27500|MT27710'


class GuestImages:
    IMAGE_DIR = '/home/wrsroot/images'
    DEFAULT_GUEST = 'tis-centos-guest'
    TIS_GUEST_PATTERN = 'cgcs-guest|tis-centos-guest'
    GUESTS_NO_RM = ['ubuntu_14', 'tis-centos-guest', 'cgcs-guest']
    # DEFAULT_GUEST = 'cgcs-guest.img'
    # Image files name and size from yow-cgcs-test.wrs.com:/home/svc-cgcsauto/images
    IMAGE_FILES = {
        'ubuntu_14': ('ubuntu-14.04-server-cloudimg-amd64-disk1.img', 8, 'ubuntu_14.qcow2'),
        'ubuntu_12': ('ubuntu-12.04-server-cloudimg-amd64-disk1.img', 8, 'ubuntu_12.qcow2'),
        'centos_6': ('CentOS-6.8-x86_64-GenericCloud-1608.qcow2', 8, 'centos_6.qcow2'),
        'centos_7': ('CentOS-7-x86_64-GenericCloud.qcow2', 8, 'centos_7.qcow2'),
        'rhel_6': ('rhel-6.5-x86_64.qcow2', 11, 'rhel_6.qcow2'),                # OVP img
        'rhel_7': ('rhel-7.2-x86_64.qcow2', 11, 'rhel_7.qcow2'),               # OVP img
        'opensuse_11': ('openSUSE-11.3-x86_64.qcow2', 11, 'opensuse_11.qcow2'),     # OVP img
        'opensuse_12': ('openSUSE-12.3-x86_64.qcow2', 21, 'opensuse_12.qcow2'),      # OVP img
        'opensuse_13': ('openSUSE-13.2-OpenStack-Guest.x86_64-0.0.10-Build2.94.qcow2', 16, 'opensuse_13.qcow2'),
        'win_2012': ('win2012r2.qcow2', 36, 'win_2012.qcow2'),   # Service Team img
        'cgcs-guest': (None, 1, 'cgcs-guest.img'),       # wrl
        'tis-centos-guest': (None, 5, 'latest_tis-centos-guest.img')
    }


class Networks:
    MGMT_NET_NAME = 'tenant\d-mgmt-net'
    DATA_NET_NAME = 'tenant\d-net'
    INTERNAL_NET_NAME = 'internal'
    # such as 192.168.11.6
    MGMT_IP = r'192.168.\d{1,3}.\d{1,3}'
    # such as 172.16.1.11
    DATA_IP = r'172.\d{1,3}.\d{1,3}.\d{1,3}'
    # such as 10.1.1.44
    INTERNAL_IP = r'10.\d{1,3}.\d{1,3}.\d{1,3}'


class SystemType:
    CPE = 'CPE'
    STANDARD = 'Standard'


class HostStorageBacking:
    LOCAL_LVM = 'local_storage_lvm_hosts'
    LOCAL_IMAGE = 'local_storage_image_hosts'
    REMOTE = 'remote_storage_hosts'


class VMStatus:
    # under http://docs.openstack.org/developer/nova/vmstates.html
    ACTIVE = 'ACTIVE'
    BUILD = 'BUILDING'
    REBUILD = 'REBUILD'
    VERIFY_RESIZE = 'VERIFY_RESIZE'
    RESIZE = 'RESIZED'
    ERROR = 'ERROR'
    SUSPENDED = 'PAUSED'
    PAUSED = 'PAUSED'
    NO_STATE = 'NO STATE'
    HARD_REBOOT = 'HARD REBOOT'
    SOFT_REBOOT = 'REBOOT'
    STOPPED = "SHUTOFF"
    MIGRATING = 'MIGRATING'


class HostAdminState:
    UNLOCKED = 'unlocked'
    LOCKED = 'locked'


class HostOperationalState:
    ENABLED = 'enabled'
    DISABLED = 'disabled'


class HostAvailabilityState:
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
    TENANT1_PROMPT = '\[wrsroot@controller\-[01] ~\(keystone_tenant1\)\]\$ '
    TENANT2_PROMPT = '\[wrsroot@controller\-[01] ~\(keystone_tenant2\)\]\$ '
    COMPUTE_PROMPT = '.*compute\-([0-9]){1,}\:~\$'
    STORAGE_PROMPT = '.*storage\-([0-9]){1,}\:~\$'
    PASSWORD_PROMPT = '.*assword\:.*'
    BUILD_SERVER_PROMPT_BASE = '{}@{}\:~.*'
    ADD_HOST = '.*\(yes/no\).*'
    ROOT_PROMPT = '.*root@.*'
    Y_N_PROMPT = '.*\(y/n\)\?.*'
    YES_N_PROMPT = '.*\[yes/N\]\: ?'



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
    CPU_THREAD_POLICY = 'hw:cpu_thread_policy'
    VCPU_SCHEDULER = 'hw:wrs:vcpu:scheduler'
    MIN_VCPUS = "hw:wrs:min_vcpus"
    STORAGE_BACKING = 'aggregate_instance_extra_specs:storage'
    # LOCAL_STORAGE = 'aggregate_instance_extra_specs:localstorage'
    DISK_READ_BYTES = 'quota:disk_read_bytes_sec'
    DISK_READ_IOPS = 'quota:disk_read_iops_sec'
    DISK_WRITE_BYTES = 'quota:disk_write_bytes_sec'
    DISK_WRITE_IOPS = 'quota:disk_write_iops_sec'
    DISK_TOTAL_BYTES = 'quota:disk_total_bytes_sec'
    DISK_TOTAL_IOPS = 'quota:disk_total_iops_sec'
    NUMA_NODES = 'hw:numa_nodes'
    NUMA_0 = 'hw:numa_node.0'
    NUMA_1 = 'hw:numa_node.1'
    NUMA0_CPUS = 'hw:numa_cpus.0'
    NUMA1_CPUS = 'hw:numa_cpus.1'
    NUMA0_MEM = 'hw:numa_mem.0'
    NUMA1_MEM = 'hw:numa_mem.1'
    VSWITCH_NUMA_AFFINITY = 'hw:wrs:vswitch_numa_affinity'
    MEM_PAGE_SIZE = 'hw:mem_page_size'
    AUTO_RECOVERY = 'sw:wrs:auto_recovery'
    GUEST_HEARTBEAT = 'sw:wrs:guest:heartbeat'
    SRV_GRP_MSG = "sw:wrs:srv_grp_messaging"
    NIC_ISOLATION = "hw:wrs:nic_isolation"
    PCI_NUMA_AFFINITY = "hw:wrs:pci_numa_affinity"
    PCI_PASSTHROUGH_ALIAS = "pci_passthrough:alias"
    PCI_IRQ_AFFINITY_MASK = "hw:pci_irq_affinity_mask"


class ImageMetadata:
    MEM_PAGE_SIZE = 'hw_mem_page_size'
    AUTO_RECOVERY = 'sw_wrs_auto_recovery'
    VIF_MODEL = 'hw_vif_model'
    CPU_THREAD_POLICY = 'hw_cpu_thread_policy'
    CPU_POLICY = 'hw_cpu_policy'


class ServerGroupMetadata:
    BEST_EFFORT = "wrs-sg:best_effort"
    GROUP_SIZE = "wrs-sg:group_size"


class InstanceTopology:
    NODE = 'node:(\d),'
    PGSIZE = 'pgsize:(\d{1,3}),'
    VCPUS = 'vcpus:(\d{1,2}),'
    PCPUS = 'pcpus:(\d{1,2}),\s'     # find a string separated by ',' if multiple numa nodes
    CPU_POLICY = 'pol:(.*),'
    SIBLINGS = 'siblings:(.*),'
    THREAD_POLICY = 'thr:(.*)$|thr:(.*),'
    TOPOLOGY = '\d{1,2}s,\d{1,2}c,\d{1,2}t'


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
    VM_REBOOTING = '700.005'
    STORAGE_DEGRADE = '200.006'
    STORAGE_ALARM_COND = '800.001'
    STORAGE_LOR = '800.011'
    STORAGE_POOLQUOTA = '800.003'
    HOST_LOCK = '200.001'
    NETWORK_AGENT_NOT_RESPOND = '300.003'
    CON_DRBD_SYNC = '400.001'
    SERVICE_GROUP_STATE_CHANGE = '400.001'
    MTC_MONITORED_PROCESS_FAILURE = '200.006'


class NetworkingVmMapping:
    VSWITCH = {
        'vif': 'avp',
        'flavor': 'medium.dpdk',
    }
    AVP = {
        'vif': 'avp',
        'flavor': 'small',
    }
    VIRTIO = {
        'vif': 'avp',
        'flavor': 'small',
    }


class VifMapping:
    VIF_MAP = {'vswitch': 'DPDKAPPS',
               'avp': 'AVPAPPS',
               'virtio': 'VIRTIOAPPS',
               'sriov': 'SRIOVAPPS',
               'pcipt': 'PCIPTAPPS'
               }


class LocalStorage:
    DIR_PROFILE = 'storage_profiles'
    TYPE_STORAGE_PROFILE = ['storageProfile', 'localstorageProfile']


class VMNetworkStr:
    NET_IF = r"auto {}\niface {} inet dhcp\n"


class HTTPPorts:
    NEUTRON_PORT = 9696
    NEUTRON_VER = "v2.0"
    CEIL_PORT = 8777
    CEIL_VER = "v2"
    SYS_PORT = 6385
    SYS_VER = "v1"
    CINDER_PORT = 8776
    CINDER_VER = "v2"   # v1 is also supported
    GLANCE_PORT = 9292
    GLANCE_VER = "v2"
    HEAT_PORT = 8004
    HEAT_VER = "v1"
    HEAT_CFN_PORT = 8000
    HEAT_CFN_VER = "v1"
    NOVA_PORT = 8774
    NOVA_VER = "v2"     # v3 also supported
    NOVA_EC2_PORT = 8773
    NOVA_EC2_VER = "v2"
    PATCHING_PORT = 15491
    PATCHING_VER = "v1"


class CeilometerSamples:
    VSWITCH_PORT_TRANSMIT_UTIL = "vswitch.port.transmit.util"
    VSWITCH_ENGINE_UTIL = "vswitch.engine.util"


class QoSSpecs:
    READ_BYTES = 'read_bytes_sec'
    WRITE_BYTES = 'write_bytes_sec'
    TOTAL_BYTES = 'total_bytes_sec'
    READ_IOPS = 'read_iops_sec'
    WRITE_IOPS = 'write_iops_sec'
    TOTAL_IOPS = 'total_iops_sec'

