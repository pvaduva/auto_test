class Nodes:
    CONTROLLER_CEPH = {
        'node_type': 'controller_ceph',
        'memory': 8192,
        'cpus': 2,
        'disks': [120000],
    }

    CONTROLLER_LVM = {
        'node_type': 'controller_lvm',
        'memory': 8192,
        'cpus': 2,
        'disks': [100000, 10000],
    }

    CONTROLLER_AIO = {
        'node_type': 'controller_aio',
        'memory': 12288,
        'cpus': 4,
        'disks': [240000, 40000],
    }

    COMPUTE = {
        'node_type': 'compute',
        'memory': 4096,
        'cpus': 3,
        'disks': [50000, 30000],
    }

    STORAGE = {
        'node_type': 'storage',
        'memory': 3072,
        'cpus': 1,
        'disks': [50000, 10000],
    }
