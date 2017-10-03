class SkipReason:
    PCI_IF_UNAVAIL = "SRIOV and PCI-passthrough interface override info not found in lab_setup.conf"
    PCIPT_IF_UNAVAIL = "PCI-passthrough interface override info not found in lab_setup.conf"
    SRIOV_IF_UNAVAIL = "SRIOV interface override info not found in lab_setup.conf"
    LESS_THAN_TWO_HT_HOSTS = "Less than two hyperthreaded hosts available"
    MORE_THAN_ONE_HT_HOSTS = "More than one hyperthreaded hosts available"
    LESS_THAN_TWO_HYPERVISORS = "Less than two hypervisors available"
    CPE_DETECTED = "Skip for small footprint lab"
    NO_HOST_WITH_BACKING = "No host with {} instance storage backing exists on system"
    LESS_THAN_TWO_HOSTS_WITH_BACKING = "Less than two hosts with {} instance storage backing exist on system"
    SMALL_CINDER_VOLUMES_POOL = "Cinder Volumes Pool is less than 30G"
    LESS_THAN_TWO_CONTROLLERS = "Less than two controllers on system"
    SIMPLEX_SYSTEM = 'Not applicable to Simplex system'
    SIMPLEX_ONLY = 'Only applicable to Simplex system'
    INSUFFICIENT_IMG_CONV = 'Insufficient image-conversion space to convert {} image to raw format'
