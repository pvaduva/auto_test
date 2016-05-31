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


class MinCPUErr:
    VAL_LARGER_THAN_VCPUS = "min_vcpus must be less than or equal to the flavor vcpus value"
    VAL_LESS_THAN_1 = "min_vcpus must be greater than or equal to 1"
    CPU_POLICY_NOT_DEDICATED = "min_vcpus is only valid when hw:cpu_policy is 'dedicated'"


class CpuAssignment:
    VSWITCH_TOO_MANY_CORES = "The vswitch function can only be assigned up to 8 core"
    TOTAL_TOO_MANY_CORES = "More total logical cores requested than present on 'Processor {}'"
    NO_VM_CORE = "There must be at least one unused core for VMs."

