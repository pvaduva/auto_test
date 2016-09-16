class VCPUSchedulerErr:
    CANNOT_SET_VCPU0 = "vcpu 0 cannot be specified"
    VCPU_VAL_OUT_OF_RANGE = "vcpu value out of range"
    INVALID_PRIORITY = "priority must be between 1-99"
    PRIORITY_NOT_INTEGER = "priority must be an integer"
    INVALID_FORMAT = "invalid format"
    UNSUPPORTED_POLICY = "not a supported policy"
    POLICY_MUST_SPECIFIED_LAST = "policy/priority for all vcpus must be specified last"
    MISSING_PARAMETER = "missing required parameter"
    TOO_MANY_PARAMETERS = "too many parameters"
    VCPU_MULTIPLE_ASSIGNMENT = "specified multiple times, specification is ambiguous"
    CPU_MODEL_UNAVAIL = "No valid host was found.*Host VCPU model.*required.*"


class MinCPUErr:
    VAL_LARGER_THAN_VCPUS = "min_vcpus must be less than or equal to the flavor vcpus value"
    VAL_LESS_THAN_1 = "min_vcpus must be greater than or equal to 1"
    CPU_POLICY_NOT_DEDICATED = "min_vcpus is only valid when hw:cpu_policy is 'dedicated'"


class ScaleErr:
    SCALE_LIMIT_HIT = "When scaling, cannot scale beyond limits"


class CpuAssignment:
    VSWITCH_TOO_MANY_CORES = "The vswitch function can only be assigned up to 8 core"
    TOTAL_TOO_MANY_CORES = "More total logical cores requested than present on 'Processor {}'"
    NO_VM_CORE = "There must be at least one unused core for VMs."
    VSWITCH_INSUFFICIENT_CORES = "The vswitch function must have at least {} core(s)"


class CPUThreadErr:
    INVALID_POLICY = "Invalid hw:cpu_thread_policy '{}', must be one of: require, isolate, prefer."
    DEDICATED_CPU_REQUIRED = 'Cannot set cpu thread pinning policy in a non dedicated cpu pinning policy'
    VCPU_NUM_UNDIVISIBLE = "(NUMATopologyFilter) Cannot use 'require' cpu threads policy as requested #VCPUs: {}, " \
                           "is not divisible by number of threads: 2"
    INSUFFICIENT_CORES_FOR_ISOLATE = "{}: (NUMATopologyFilter) Cannot use isolate cpu thread policy as requested " \
                                     "VCPUS: {} is greater than available CPUs with all siblings free"
    HT_HOST_UNAVAIL = "(NUMATopologyFilter) Host not useable. Requested threads policy: '{}'; from flavor or image " \
                      "is not allowed on non-hyperthreaded host"
    UNSET_SHARED_VCPU = "Cannot set hw:cpu_thread_policy to {} if hw:wrs:shared_vcpu is set. Either unset " \
                        "hw:cpu_thread_policy, set it to prefer, or unset hw:wrs:shared_vcpu"
    UNSET_MIN_VCPUS = "Cannot set hw:cpu_thread_policy to {} if hw:wrs:min_vcpus is set. Either unset " \
                      "hw:cpu_thread_policy, set it to another policy, or unset hw:wrs:min_vcpus"
    CONFLICT_FLV_IMG = "Image property 'hw_cpu_thread_policy' is not permitted to override CPU thread pinning policy " \
                       "set against the flavor"


class CPUPolicyErr:
    CONFLICT_FLV_IMG = "Image property 'hw_cpu_policy' is not permitted to override CPU pinning policy set against " \
                       "the flavor "


class SharedCPUErr:
    DEDICATED_CPU_REQUIRED = "hw:wrs:shared_vcpu is only valid when hw:cpu_policy is dedicated"
    INVALID_VCPU_ID = "hw:wrs:shared_vcpu must be greater than or equal to 0"
    MORE_THAN_FLAVOR = "hw:wrs:shared_vcpu value ({}) must be less than flavor vcpus ({})"


class ResizeVMErr:
    RESIZE_ERR = "Error resizing server"


class ColdMigErr:
    HT_HOST_REQUIRED = "(NUMATopologyFilter) Host not useable. Requested threads policy: {} from flavor or image is " \
                       "not allowed on non-hyperthreaded host"


class LiveMigErr:
    BLOCK_MIG_UNSUPPORTED = "is not on local storage: Block migration cannot be used with shared storage"


class NetworkingErr:
    INVALID_VXLAN_VNI_RANGE = "exceeds 16777215"
    INVALID_MULTICAST_IP_ADDRESS = "is not a valid multicast IP address."
    INVALID_VXLAN_PROVISION_PORTS = "is not in [4789, 8472]."
    VXLAN_TTL_RANGE_MISSING = "VXLAN time-to-live attributes missing"
    VXLAN_TTL_RANGE_TOO_LARGE = "is too large - must be no larger than '255'."
    OVERLAP_SEGMENTATION_RANGE = "segmentation id range overlaps with"
    INVALID_MTU_VALUE = "requires an interface MTU value of at least"
    VXLAN_MISSING_IP_ON_INTERFACE = "requires an IP address"
    WRONG_IF_ADDR_MODE = "interface address mode must be 'static'"
    SET_IF_ADDR_MODE_WHEN_IP_EXIST = "addresses still exist on interfac"
    NULL_IP_ADDR = "Address must not be null"
    NULL_NETWORK_ADDR = "Network must not be null"
    NULL_GATEWAY_ADDR = "Gateway address must not be null"
    NULL_HOST_PARTION_ADDR = "Host bits must not be zero"
    NOT_UNICAST_ADDR = "Address must be a unicast address"
    NOT_BROADCAST_ADDR = "Address cannot be the network broadcast address"
    DUPLICATE_IP_ADDR = "already exists"
    INVALID_IP_OR_PREFIX = "Invalid IP address and prefix"
    INVALID_IP_NETWORK = "Invalid IP network"
    ROUTE_GATEWAY_UNREACHABLE = "not reachable"
    IP_VERSION_NOT_MATCH = "Network and gateway IP versions must match"
    GATEWAY_IP_IN_SUBNET = "Gateway address must not be within destination subnet"
    NETWORK_IP_EQUAL_TO_GATEWAY = "Network and gateway IP addresses must be different"
