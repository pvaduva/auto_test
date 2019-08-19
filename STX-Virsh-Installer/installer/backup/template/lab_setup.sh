#!/bin/bash -eu

PLATFORM_CONF=${PLATFORM_CONF:-"/etc/platform/platform.conf"}
STATUS_FILE=${STATUS_FILE:-"${HOME}/.lab_setup.done"}
GROUP0_FILE=${GROUP0_FILE:-"${HOME}/lab_setup_group0.conf"}
CONFIG_CHAIN_FILE=${CONFIG_CHAIN_FILE:-"${HOME}/.config_chain"}
VERBOSE_LEVEL=0
DEBUG_LEVEL=0
FORCE="no"
CLEAR_CHAIN="no"
RAM_QUOTA=""

DEFAULT_IF0=eth0
DEFAULT_IF1=eth1
DEFAULT_IF2=eth2

CLI_NOWRAP=--nowrap
DEFAULT_OPENSTACK_PASSWORD="Li69nux*"
K8S_ENABLED="yes"
K8S_URL="http://keystone.openstack.svc.cluster.local/v3"

## Pause first-time configuration to allow the user to setup the
## controller/worker nodes.  Unset or set to "no" to allow the script to run
## to completion without any pauses.
##
PAUSE_CONFIG=${PAUSE_CONFIG:-"yes"}

while getopts :f:cvdzF OPT; do
    case $OPT in
        F|+F)
            FORCE="yes"
            ;;
        f|+f)
            set +u 
            CONFIG_FILES="$CONFIG_FILES $OPTARG"
            set -u
            ;;
        c|+c)
            PAUSE_CONFIG="no"
            ;;
        v|+v)
            VERBOSE_LEVEL=$((VERBOSE_LEVEL + 1))
            ;;
        d|+d)
            DEBUG_LEVEL=$((DEBUG_LEVEL + 1))
            ;;
        z|+z)
            CLEAR_CHAIN="yes"
            ;;
        *)
            echo "usage: ${0##*/} [-f config_file] [-c] [-v] [-d] [-z] [--] ARGS..."
            exit 2
    esac
done
shift $(( OPTIND - 1 ))
OPTIND=1

CONFIG_FILES=${CONFIG_FILES:-"${HOME}/lab_setup.conf"}

## Run as admin
OPENRC=/etc/platform/openrc
source ${OPENRC}

## Determine board configuration
if [ ! -f ${PLATFORM_CONF} ]; then
    echo "Failed to find ${PLATFORM_CONF}"
    exit 3
fi
source ${PLATFORM_CONF}

# --os-region-name option is required for cinder, glance, nova and neutron commands on
# SystemController in Distributed Cloud configuration
if [[ -n ${distributed_cloud_role+x} && "${distributed_cloud_role}" == "systemcontroller" ]]; then
    REGION_OPTION="--os-region-name SystemController"
else
    REGION_OPTION=""
fi

if [[ "${subfunction}" == *worker* ]]; then
    ## A small (combined) system
    SMALL_SYSTEM="yes"
    NODES=$(system host-list ${CLI_NOWRAP} | awk '{if (($6 == "controller" || $6 == "worker") && ($12 != "offline")) print $4;}')
else
    SMALL_SYSTEM="no"
    NODES=$(system host-list ${CLI_NOWRAP} | awk '{if ($6=="worker" && ($12 != "offline")) print $4;}')
fi

if [[ "${subfunction}" == *lowlatency* ]]; then
    LOW_LATENCY="yes"
else
    LOW_LATENCY="no"
fi

## Get system mode
SYSTEM_MODE=${system_mode:-none}
#Distributed cloud role: controller, subcloud, none
DISTRIBUTED_CLOUD_ROLE="none"

## vswitch type
VSWITCH_TYPE="avs"

## Controller nodes
## (controller-0 is configured by config_controller)
CONTROLLER_NODES="controller-0 controller-1"


## File System storage size
DATABASE_FS_SIZE=0
BACKUP_FS_SIZE=0

FS_RESIZE_TIMEOUT=180
FS_RESIZE_DEGRADE_TIMEOUT=120

# 60 minutes
DRBD_SYNC_TIMEOUT=3600

## Common resource names and prefixes
##
GROUPNO=0

TENANT1=tenant1
TENANT2=tenant2

## The openstack user domain for creation of tenant user.
## The openstack project domain for creation of tenant projects.
## Since these are mapped to the SQL based Identity backend, they
## shall go into the Default domain.
OPENSTACK_USER_DOMAIN="default"
OPENSTACK_PROJECT_DOMAIN="default"

ADMIN_USER="admin"
MEMBER_ROLE="member"

## Numa node testing.  Set to "node0", "node1", or "float" to set the numa
## node for a specific tenant.  By default the tenant VMs are pinned to cpus
## but not on a specific numa node.
##
TENANT1NODE=""
TENANT2NODE=""

## The maximum number of NUMA nodes of the system
##
NUMA_NODE_COUNT=2

## Tenant network configurations.
##
DNSNAMESERVERS="147.11.57.133 128.224.144.130 147.11.57.128"
MGMTIPVERSION=4
MGMTNETS=1
MGMTSUBNETS=("192.168.101.0/27,192.168.101.32/27,192.168.101.64/27", "192.168.201.0/27,192.168.201.32/27,192.168.201.64/27")
MGMTDVR=("no" "no")
MGMTIPV6ADDRMODE="dhcpv6-stateful"
EXTIPVERSION=4
EXTERNALGWIP="192.168.1.1"
EXTERNALCIDR="192.168.1.0/24"
EXTERNALSNAT="no"


## Provider network configurations. Each lab has dedicated VLANs assigned to it.
## An exception to this is that the external network VLAN is shared across all
## of the labs.  The configuration syntax which is describes belows allows to
## define an arbitrary number of provider networks on a per lab basis and then
## to refer to those provider networks by name when defining data interfaces.
## Since in the large lab configuration we need to distinguish provider
## networks from each group/island we prefix their name with "groupX-" where X
## is the group number.  To avoid having to specify the group number in several
## places we leave it off of all variable specifications and the prefix is
## added dynamically where needed.  For example, "ext0" below will become
## "group0-ext0" when actually created; and "data0" will become "group0-data0"
## when created.
##
## Example:
##
## PROVIDERNETS="vxlan|ext0|1500|4-4|shared|239.0.2.1|4789|11 \
## vlan|data0|1500|600-615|tenant1 \
## vlan|data0b|1500|700-731|shared \
## vlan|data1|1500|616-631|tenant2"
##
PROVIDERNETS="vlan|ext0|1500|10-10|shared \
vlan|data0|1500|600-615|tenant1 \
vlan|data0b|1500|700-731|shared \
vlan|data1|1500|616-631|tenant2"

## Enable vlan transparency on all provider networks that have not provided a
## setting for this feature.  For now this is a global attribute.  In the
## future we will add control on a per provider network and tenant network
## basis.
##
VLAN_TRANSPARENT="False"


## Enable vlan transparency on internal networks.  This is an alternative to
## using trunks, and if True, then trunks will not be provisioned.
VLAN_TRANSPARENT_INTERNAL_NETWORKS="True"

## Tenant network provider network manual configurations.  Because our lab
## environment dictates that we use specific VLAN values for specific tenants
## (i.e., to reach NAT box, or to be carried by specific data interface) we
## need to manual set the provider network and segmentation id values.
##
EXTERNALPNET="vlan|ext0|10"
INTERNALPNET="vlan|data0b"



## VXLAN specific attributes.  The GROUP and PORT array can have multiple
## values.  The 0th entry will be used for the tenant1 provider network
## ranges, the Nth entry will be used for the tenant2 provider networ ranges,
## and the internal network ranges will alternate between each value therefore
## allowing for a mixture of addresses and ports in the configuration.  Each
## internal range will have up to VXLAN_INTERNAL_STEP entries
##
VXLAN_GROUPS="239.0.1.1 ff0e::1:1 239.0.1.2 ff0e::1:2"
VXLAN_PORTS="8472 4789"
VXLAN_TTL=1
VXLAN_INTERNAL_STEP=4

## Set the default VIF model of the first NIC on all VM instances to "virtio".
## Do not change this as it may cause unintended side-effects and NIC
## reordering in the VM.
MGMT_VIF_MODEL="virtio"

## Common paths
IMAGE_DIR=${HOME}/images
USERDATA_DIR=${HOME}/userdata

## Networking test mode
## choices={"layer2", "layer3"}
##
NETWORKING_TYPE="layer3"

## Provider Network type
## choices={"vlan", "vxlan", "mixed"}
##
## warning: If setting to "vxlan" there must be a DATA0IPADDR and DATA1IPADDR
## set for each worker node.
PROVIDERNET_TYPE="vlan"

## Special test mode for benchmarking only.  Set to "yes" only if only a
## single VM pair will exist at any given time.  This will cause only a single
## pair of tenant and internal networks to be created.  This is to facilitate
## sequentially booting and taring down VMs of different types to benchmark
## their network performance without having to cleanup the lab and install a
## different configuration.
##
REUSE_NETWORKS="no"

## Special test mode for benchmarking only.  Set to "yes" to force tenant
## networks to be shared so that a single VM can have a link to each tenant's
## tenant network.  This is to force traffic from ixia to be returned directly
## to ixia without first passing through an internal network and another VM.
## In this mode it is expected that only a single tenant's VM will be launched
## at any given time (i.e., it will not work if 2 VMs are both sharing each
## others tenant network).
##
##  resulting in:
##
##      ixia-port0 +---+ tenant1-net0 +------+
##                                           VM (tenant1)
##      ixia-port1 +---+ tenant2-net0 +------+
##
##  instead of:
##
##      ixia-port0 +---+ tenant1-net0 +------+ VM (tenant1) ---+
##                                                             |
##                                                        internal-net0
##                                                             |
##      ixia-port1 +---+ tenant2-net0 +------+ VM (tenant2) ---+
##
SHARED_TENANT_NETWORKS="no"

## Special test mode for benchmarking only.  Set to "yes" to create a separate
## tenant network and router which will sit between Ixia and the regular layer2
## tenant networks.  The purpose is to insert an AVR router in to the Ixia
## traffic path so that its performance can be evaluated by vbenchmark.  This
## requires that SHARED_TENANT_NETWORKS be set to "yes" because the end goal is
## to have a single VM bridge traffic between 2 tenant networks.
##
##  resulting in:
##
##      ixia-port0 +---+ tenant1-ixia-net0 +---+ router +---+ tenant1-net0 +------+
##                                                                                VM (tenant1)
##      ixia-port1 +---+ tenant2-ixia-net0 +---+ router +---+ tenant2-net0 +------+
##
##
##  instead of:
##
##      ixia-port0 +---+ tenant1-net0 +------+
##                                           VM (tenant1)
##      ixia-port1 +---+ tenant2-net0 +------+
##
ROUTED_TENANT_NETWORKS="no"

## Enables/Disables the allocation of floating IP addresses for each VM.  This
## functionality is disabled by default because our NAT box is configured with
## static routes that provide connectivity directly to the tenant networks.
## The NAT box, as its name implies, already does NAT so we do not need this
## for day-to-day lab usage.  It should be enabled when explicitly testing
## this functionality.
FLOATING_IP="no"

## DHCP on secondary networks
##
INTERNALNET_DHCP="yes"
TENANTNET_DHCP="yes"

## to only create the first NIC on each VM.
EXTRA_NICS="yes"

## Enable config-drive instead of relying only on the metadata server
##
CONFIG_DRIVE="no"

## Force DHCP servers to service metadata requests even if there are routers on
## the network that are capable of this functionality.  Useful for SDN testing
## because routers exist but are implemented in openflow rules and are not
## capable of servicing metadata requests.
##
FORCE_METADATA="no"

## Root disk volume type and image size in GB
## choices={"glance", "cinder"}
##
IMAGE_TYPE="cinder"
IMAGE_SIZE=2
IMAGE_NAME="tis-centos-guest"
IMAGE_DIR=${HOME}/images
IMAGE_FORMAT=raw
CINDER_TIMEOUT=180

## Number of vswitch/shared physical CPU on worker nodes on first numa node
## The PCPU assignment can also be specified as a mapping between numa node and count
## with the following format.
##   XXXX_PCPU_MAP="<numa-node>:<count>,<numa-node>:<count>"
SHARED_PCPU=0

## Setup custom images for each VM type if necessary
DPDK_IMAGE=${IMAGE_NAME}
AVP_IMAGE=${IMAGE_NAME}
VIRTIO_IMAGE=${IMAGE_NAME}
SRIOV_IMAGE=${IMAGE_NAME}
PCIPT_IMAGE=${IMAGE_NAME}
VHOST_IMAGE=${IMAGE_NAME}

## Setup custom VCPU model for each VM type if necessary
##
DPDK_VCPUMODEL="SandyBridge"

## Add extra functions to guest userdata
##
#EXTRA_FUNCTIONS="pgbench"
EXTRA_FUNCTIONS=""

## Maximum number of networks physically possible in this lab
##
MAXNETWORKS=1

## If the Ixia port has less MAX throughput than the NIC under test, we
## use more than 1 Ixia port to achieve the desired line rate. This variable
## specifies port pairs to acheive the desired line rate.
IXIA_PORT_PAIRS=1

## Maximum number of VLANs per internal network
##
MAXVLANS=1
FIRSTVLANID=0

## Controls the number of VM instances that share the tenant data networks that
## go to ixia.  This exists to allow more VM instances in labs without having
## to increase the number of VLAN instances allocated to the lab.  This only
## works for NETWORKING_TYPE=layer3.
##
VMS_PER_NETWORK=1

## Enable/disable VIRTIO multi-queue support
VIRTIO_MULTIQUEUE="false"

## Custom Flavors to create
## type or a string with parameters, e.g.
##   FLAVORS="<name>|id=1000,cores=1|mem=512|disk=2|dedicated|heartbeat|numa_node.0=0|numa_node.1=0|numa_nodes=2|vcpumodel=SandyBridge|sharedcpus"
##    - <name> is required
##    - id - number
##    - cores 1-N
##    - mem in MB,
##    - disk in GB (volume size), use
##    - dedicated - dedicated if in list used, otherwise not
##    - heartbeat - heartbeat if in list, otherwise not
##    - numa_node.0 - Pin guest numa node 0 to a physical numa node.  Default not pinned
##    - numa_node.1 - Pin guest numa node 1 to a physical numa node.  Default not pinned
##    - numa_nodes - Expose guest to specified number of numa cores (spread across zones)
##    - storage - Nova storage host: local_lvm (default), local_image, remote
##    - vcpumodel - default Sandy Bridge
##    - sharedcpus - default disabled
## If multiple flavors, append them with space between:
##    FLAVORS="flavor1|cores=1|mem=512|disk=2 flavor2|cores=2|mem=1024,disk=4"
## Default values
FLAVORS=""

## Number of VMs to create.  This can be simply a number for each interface
## type or a string with parameters, e.g.
##   AVPAVPAPPS="2|flavor=small|disk=2|image=tis-centos-guest|dbench|glance|voldelay|volwait"
##    - Interface type is defined by the name (AVPAPPS, VIRTIOAPPS, DPDKAPPS, SRIOVAPPS, or PCIPTAPPS)
##    - Only the first parameter is (# of VM pairs) required. Absence means use default
##    - First number is number of pairs to create
##    - flavor - template flavor name to use for defaults, default is default flavor for the app type
##    - disk in GB (volume size), use
##    - image is template image file name - Image type raw and filename extension .img is assumed
##    - imageqcow2 is template qcow2 image file name.  Image type qcow2 and filename extension qcow2 is assumed.
##    - cache_raw - do background caching of qcow2 image to raw
##    - glance - use glance (default is IMAGE_TYPE) Note:  use voldelay with this to prevent volume creation
##    - dbench - enable dbench in VM, default is disabled
##    - nopoll - Don't poll in boot line for VM.  Allows faster booting of VMs
##    - voldelay - Delay creating volume until VM boot if present, otherwise create volume initially (N/A if using glance)
##    - volwait - If using voldelay, will wait for volume creation in volume launch, otherwise no wait (N/A if using glance)
## AVPAPPS=2 would remain legal (all defaults)
## If multiple AVP flavors of same type, append them with space between:
##    AVPAPPS="2|flavor=small|disk=2 4|flavor=large|disk=4"
## Default values
DPDKAPPS=0
AVPAPPS=0
VIRTIOAPPS=0
SRIOVAPPS=0
PCIPTAPPS=0
VHOSTAPPS=0

## Default flavors (if you change any of these make sure that
## setup_minimal_flavors creates the required flavors otherwise set
## FLAVOR_TYPES="all"
##
DPDKFLAVOR="medium.dpdk"
AVPFLAVOR="small"
VIRTIOFLAVOR="small"
SRIOVFLAVOR="small"
PCIPTFLAVOR="small"
VHOSTFLAVOR="medium.dpdk"

## Set to "all" if you want additional flavors created; otherwise only the
## ones in DPDKFLAVOR, AVPFLAVOR, VIRTIOFLAVOR, SRIOVFLAVOR, and PCIPTFLAVOR will be created
FLAVOR_TYPES="minimal"

## Network QoS values
EXTERNALQOS="external-qos"
INTERNALQOS="internal-qos"
EXTERNALQOSWEIGHT=16
INTERNALQOSWEIGHT=4
MGMTQOSWEIGHT=8

NEUTRON_PORT_SECURITY=""

## Timeout to wait for system service-parameter-apply to complete
SERVICE_APPLY_TIMEOUT=30

## PCI vendor/device IDs
PCI_VENDOR_VIRTIO="0x1af4"
PCI_DEVICE_VIRTIO="0x1000"
PCI_DEVICE_MEMORY="0x1110"
PCI_SUBDEVICE_NET="0x0001"
PCI_SUBDEVICE_AVP="0x1104"

for CONFIG_FILE in $CONFIG_FILES; do
    if [ ! -f "${CONFIG_FILE}" ]; then
        ## If any of the config files is missing then check to see if the group0
        ## file exists
        echo "Missing config file: $CONFIG_FILE, falling back to ${GROUP0_FILE}"
        CONFIG_FILES=${GROUP0_FILE}
    fi
done

for CONFIG_FILE in $CONFIG_FILES; do
    if [ ! -f "${CONFIG_FILE}" ]; then
        ## User must provide lab specific details
        echo "Missing config file: ${CONFIG_FILE}."
        exit 1
    fi
done

trim()
{
    local trimmed="$1"

    # Strip leading space.
    trimmed="${trimmed## }"
    # Strip trailing space.
    trimmed="${trimmed%% }"

    echo "$trimmed"
}

# Reset chain by clearing the chain config file
if  [ "${CLEAR_CHAIN}" == "yes" ]; then
    rm -f ${CONFIG_CHAIN_FILE}
fi

# Chain multiple config files and source them.
# Each time we call the script with a different config file
# that file is added to the chain and will be sourced in the
# same order as they were added. 
# Subsequent call to the script don't need to include the 
# config file as a parameter as it's already in the chain
for CONFIG_FILE in $CONFIG_FILES; do
    if [ ! -f ${CONFIG_CHAIN_FILE} ]; then
        touch ${CONFIG_CHAIN_FILE}
        echo $CONFIG_FILE > ${CONFIG_CHAIN_FILE}
    else
        readarray CHAIN_CONF < ${CONFIG_CHAIN_FILE}
        ADDED=0
        for cfg_file in "${CHAIN_CONF[@]}"; do
            trim_conf="$(trim $cfg_file)"
            if [ "${trim_conf}" == "${CONFIG_FILE}" ] ; then
                ADDED=1
                break
            fi
        done

        if [ $ADDED -eq 0 ]; then
            echo $CONFIG_FILE >> $CONFIG_CHAIN_FILE
        fi
    fi
done
CONVERTED_SYSTEMS="yow-cgcs-wildcat-7_12${HOME}/lab_setup.conf yow-cgcs-r720-1_2${HOME}/lab_setup.conf yow-cgcs-hp380-1_4${HOME}/lab_setup.conf yow-cgcs-ironpass-7_12${HOME}/lab_setup.conf yow-cgcs-ironpass-18_19${HOME}/lab_setup.conf yow-cgcs-ironpass-33_36${HOME}/lab_setup.conf yow-cgcs-ironpass-37_40${HOME}/lab_setup.conf yow-cgcs-wildcat-80_84${HOME}/lab_setup.conf yow-cgcs-ironpass-1_4${HOME}/lab_setup.conf yow-cgcs-ironpass-14_17${HOME}/lab_setup.conf yow-cgcs-r720-3_7${HOME}/lab_setup.conf yow-cgcs-ironpass-5_6${HOME}/lab_setup.conf yow-cgcs-wildcat-35_60${HOME}/lab_setup.conf yow-cgcs-wildcat-69_70${HOME}/lab_setup.conf "

CONVERTED_LAB="no"
## *** WARNING ***
##
## Source the per-lab configuration settings.  Do not place any user
## overrideable variables below this line.
##
## Support for chaining config files:
## The script now supports adding additional settings from extra 
## config files and chaining such configurations.
## Example:
## ./lab_setup.sh
## ./lab_setup.sh -f add_lvm.conf
## ./lab_setup.sh -f add_ceph.conf
## ./lab_setup.sh
##
## Behavior:
## - first call will add the default lab_setup.conf file to the chain
##   and source it
## - the second call will add add_lvm.conf to the chain and source
##   lab_setup.conf and add_lvm.conf (in this order)
## - the second call will add add_ceph.conf to the chain and source
##   lab_setup.conf, add_lvm.conf and add_ceph.conf (in this order)
## - the last call will not add anything new to the chain, but will
##   source all other config files anyway in the chain.
##
## Purpose of this change is to allow adding features or config
## options to a setup, no by changing the existing config file,
## but by adding a new config file with just the new features and
## run lab_setup again.
## Thus we can have a setup without any cinder backend, run tests
## on it, then easily add LVM and/or ceph on it and run the same
## (or other tests).
##
## *** WARNING ***

readarray CHAIN_CONF < ${CONFIG_CHAIN_FILE}

for cfg_file in "${CHAIN_CONF[@]}"; do
    trim_conf="$(trim $cfg_file)"
    echo "Sourcing ${trim_conf} from the config chain"
    set +u
    source ${cfg_file}
    set -u
done

rm -f ${STATUS_FILE}

#TODO: This assumes a single config file was provided, at some point we may need to enable support for
# multiple config files on a converted system.
if [[ "${CONVERTED_SYSTEMS}" == *"${SYSTEM_NAME}${CONFIG_FILES}"*  || "${SYSTEM_NAME}" == "BIG_LAB" ]]; then
        touch ${HOME}/.heat_resources
fi
if [ -f ${HOME}/.heat_resources -a ! -f ${HOME}/.this_didnt_work ]; then
        echo "Lab setup will use heat for resources"
        touch ${HOME}/.heat_resources
        CONVERTED_LAB="yes"
fi

## Set a per-group status file
GROUP_STATUS=${STATUS_FILE}.group${GROUPNO}
LOG_FILE=${LOG_FILE:-"${HOME}/lab_setup.group${GROUPNO}.log"}

## Variables which can be affected by user overrides
##
TENANTNODES=("${TENANT1NODE}" "${TENANT2NODE}")
TENANTS=("${TENANT1}" "${TENANT2}")
PROVIDERNET0="group${GROUPNO}-data0"
PROVIDERNET1="group${GROUPNO}-data1"
EXTERNALNET="external-net${GROUPNO}"
EXTERNALSUBNET="external-subnet${GROUPNO}"
INTERNALNET="internal${GROUPNO}-net"
INTERNALSUBNET="internal${GROUPNO}-subnet"

DEFAULT_BOOTDIR=${HOME}/instances
BOOTDIR=${HOME}/instances_group${GROUPNO}
BOOTCMDS=${BOOTDIR}/launch_instances.sh
HEATSCRIPT=${BOOTDIR}/heat_instances.sh

## All combined application types
ALLAPPS="${DPDKAPPS} ${AVPAPPS} ${VIRTIOAPPS} ${SRIOVAPPS} ${PCIPTAPPS} ${VHOSTAPPS}"

## Total counts after user overrides
##
APPCOUNT=0
APPS=($ALLAPPS)
for INDEX in ${!APPS[@]}; do
    ENTRY=${APPS[${INDEX}]}
    DATA=(${ENTRY//|/ })
    NUMVMS=${DATA[0]}
    APPCOUNT=$((${APPCOUNT} + ${NUMVMS}))
done

NETCOUNT=$((${APPCOUNT} / ${VMS_PER_NETWORK}))
REMAINDER=$((${APPCOUNT} % ${VMS_PER_NETWORK}))
if [ ${REMAINDER} -ne 0 ]; then
    NETCOUNT=$((NETCOUNT+1))
fi

if [ ${NETCOUNT} -gt ${MAXNETWORKS} ]; then
    echo "Insufficient number of networks for all requested apps"
    exit 1
fi

if [ ${VMS_PER_NETWORK} -ne 1 -a ${NETWORKING_TYPE} != "layer3" ]; then
    echo "VMS_PER_NETWORK must be 1 if NETWORKING_TYPE is not \"layer3\""
    exit 1
fi

## Tenant Quotas
##    network: each tenant has a network per VM plus a mgmt network
##    subnet: each tenant has a subnet per network plus additional mgmt subnets
##    port: each tenant has 3 ports per VM, 2 ports per network (DHCP/L3),
##          1 floating-ip per VM, 1 gateway per router, plus additional manual ports
##    volume/snapshot - 2x instances to allow volume for launch script volume and heat volume
##
NETWORK_QUOTA=${NETWORK_QUOTA:-$((NETCOUNT + (2 * ${MGMTNETS})))}
SUBNET_QUOTA=${SUBNET_QUOTA:-$((NETWORK_QUOTA + 10))}
PORT_QUOTA=${PORT_QUOTA:-$(((APPCOUNT * 3) + (${NETCOUNT} * 2) + ${APPCOUNT} + 1 + 32))}
INSTANCE_QUOTA=${INSTANCE_QUOTA:-${APPCOUNT}}
CORE_QUOTA=${CORE_QUOTA:-$((INSTANCE_QUOTA * 3))}
FLOATING_IP_QUOTA=${FLOATING_IP_QUOTA:-${APPCOUNT}}
VOLUME_QUOTA=${VOLUME_QUOTA:-$((APPCOUNT * 2))}
SNAPSHOT_QUOTA=${SNAPSHOT_QUOTA:-$((APPCOUNT * 2))}

## Admin Quotas
##     network:  the admin has 1 external network, and all shared internal networks
##     subnet: the admin has 1 for the external network, and 1 subnet per pair of VM
##     port: the admin has 1 port on the external network for DHCP (if needed)
##
SHARED_NETCOUNT=${NETCOUNT}
ADMIN_NETWORK_QUOTA=${ADMIN_NETWORK_QUOTA:-$((SHARED_NETCOUNT + 2))}
ADMIN_SUBNET_QUOTA=${ADMIN_SUBNET_QUOTA:-$((NETCOUNT + 2))}
ADMIN_PORT_QUOTA=${ADMIN_PORT_QUOTA:-"10"}

## Two VMs per application pairs
VMCOUNT=$((APPCOUNT * 2))

## Prune the list of controller nodes down to the ones that are unlocked-available
TMP_CONTROLLER_NODES=${CONTROLLER_NODES}
AVAIL_CONTROLLER_NODES=""
if [ ${GROUPNO} -eq 0 ]; then
    for NODE in ${TMP_CONTROLLER_NODES}; do
        HOSTNAME=$(system host-list ${CLI_NOWRAP} | grep ${NODE} | awk '{if (($8 == "unlocked") && ($12 == "available")) {print $4;}}')
        if [ -n "${HOSTNAME}" ]; then
            AVAIL_CONTROLLER_NODES="${HOSTNAME} ${AVAIL_CONTROLLER_NODES}"
        fi
    done
fi


## Global data to help facilitate constants that vary by VM type.  These must
## all map one-to-one with the values in APPTYPES
##
APPTYPES=("PCIPT" "SRIOV" "DPDK" "AVP" "VIRTIO" "VHOST")
VMTYPES=("pcipt" "sriov" "vswitch" "avp" "virtio" "vhost")
NETTYPES=("kernel" "kernel" "vswitch" "kernel" "kernel" "vswitch")
NIC1_VIF_MODELS=("avp" "avp" "avp" "avp" "virtio" "virtio")
NIC2_VIF_MODELS=("pci-passthrough" "pci-sriov" "avp" "avp" "virtio" "virtio")
NIC1_VNIC_TYPES=("normal" "normal" "normal" "normal" "normal" "normal")
NIC2_VNIC_TYPES=("direct-physical" "direct" "normal" "normal" "normal" "normal")
CREATE_PORT_TYPES=("yes" "yes" "yes" "yes" "no" "no")

# Get system mode and type
SYSTEM_MODE=`system show | grep -i system_mode | awk '{print $4}'`
SYSTEM_TYPE=`system show | grep -i system_type | awk '{print $4}'`

DATE_FORMAT="%Y-%m-%d %T"

## Executes a command and logs the output
function log_command()
{
    local CMD=$1
    local MSG="[${OS_USERNAME}@${OS_PROJECT_NAME}]> RUNNING: ${CMD}"

    set +e
    if [ ${VERBOSE_LEVEL} -gt 0 ]; then
        echo ${MSG}
    fi
    echo $(date +"${DATE_FORMAT}") ${MSG} >> ${LOG_FILE}

    if [ ${VERBOSE_LEVEL} -gt 1 ]; then
        eval ${CMD} 2>&1 | tee -a ${LOG_FILE}
        RET=${PIPESTATUS[0]}
    else
        eval ${CMD} &>> ${LOG_FILE}
        RET=$?
    fi

    if [ ${RET} -ne 0 ]; then
        info "COMMAND FAILED (rc=${RET}): ${CMD}"
        info "==========================="
        info "Check \"${LOG_FILE}\" for more details, and re-run the failed"
        info "command manually before contacting the domain owner for assistance."
        exit 1
    fi
    set -e

    return ${RET}
}

## Log a message to screen if verbose enabled
function log()
{
    local MSG="$1"

    if [ ${VERBOSE_LEVEL} -gt 1 ]; then
        echo ${MSG}
    fi
    echo $(date +"${DATE_FORMAT}") ${MSG} >> ${LOG_FILE}
}

## Log a message to screen if debug enabled
function debug()
{
    local MSG="$1"

    if [ ${DEBUG_LEVEL} -ge 1 ]; then
        echo ${MSG}
    fi
    echo $(date +"${DATE_FORMAT}") ${MSG} >> ${LOG_FILE}
}

## Log a message to screen and file
function info()
{
    local MSG="$1"

    echo ${MSG}
    echo $(date +"${DATE_FORMAT}") ${MSG} >> ${LOG_FILE}
}

## Log a message to file and stdout
function log_warning()
{
    local MSG="WARNING: $1"

    echo ${MSG}
    echo $(date +"${DATE_FORMAT}") ${MSG} >> ${LOG_FILE}
}

## Retrieve the image id for an image name
function get_glance_id()
{
    local NAME=$1
    echo $(glance ${REGION_OPTION} image-list 2>/dev/null | grep -E "${NAME}[ \t\n]" | awk '{print $2}')
}

## Retrieve the image id for a volume name
function get_cinder_id()
{
    local NAME=$1
    echo $(cinder ${REGION_OPTION} show ${NAME} 2>/dev/null | awk '{ if ($2 == "id") {print $4} }')
}

## Retrieve the status for a volume name
function get_cinder_status()
{
    local NAME=$1
    echo $(cinder ${REGION_OPTION} show ${NAME} 2>/dev/null | awk '{ if ($2 == "status") {print $4} }')
}

## Retrieve the router id for a router name
function get_router_id()
{
    local NAME=$1
    echo $(openstack ${REGION_OPTION} router show ${NAME} -c id -f value 2>/dev/null)
}

## Retrieve the tenant id for a tenant name
function get_tenant_id()
{
    local NAME=$1
    echo $(openstack project show ${NAME} -c id 2>/dev/null | grep id | awk '{print $4}')
}

## Retrieve the user id for a user name
function get_user_id()
{
    local NAME=$1
    echo $(openstack user show ${NAME} -c id 2>/dev/null | grep id | awk '{print $4}')
}

## Retrieve the user roles for a tenant and user
function get_user_roles()
{
    local TENANT=$1
    local USERNAME=$2
    echo $(openstack role list --project ${TENANT} --user ${USERNAME} 2>/dev/null | grep ${USERNAME} | awk '{print $4}')
}

## Build the network name for a given network instance.  For backwards
## compatibility with existing testcases the first network instance has no
## number in its' name.
function get_mgmt_network_name()
{
    local PREFIX=$1
    local NUMBER=$2

    local NAME=${PREFIX}
    if [ ${NUMBER} -ne 0 ]; then
        NAME=${NAME}${NUMBER}
    fi

    echo ${NAME}
    return 0
}

## Retrieve the network id for a network name
function get_network_id()
{
    local NAME=$1
    echo $(openstack ${REGION_OPTION} network show ${NAME} -c id -f value 2>/dev/null)
}

## Retrieve the network MTU for a network id
function get_network_mtu()
{
    local ID=$1
    echo $(openstack ${REGION_OPTION} network show ${ID} -c mtu -f value 2>/dev/null)
}

## Get the fixed ip on the tenant network
function get_network_ip_address()
{
    local NETNUMBER=$1
    local HOSTNUMBER=$2
    local TENANTNUM=$3
    ## tenant1 gets VM addresses:   172.16.*.1, 172.16.*.3, 172.16.*.5
    ## tenant1 gets Ixia addresses: 172.16.*.2, 172.16.*.4, 172.16.*.6
    ## tenant2 gets VM addresses:   172.18.*.1, 172.18.*.3, 172.18.*.5
    ## tenant2 gets Ixia addresses: 172.18.*.2, 172.18.*.4, 172.18.*.6
    echo "172.$((16 + ${TENANTNUM} * 2)).${NETNUMBER}.$((1 + (${HOSTNUMBER} * 2)))"
}

## construct the nova boot arg for a fixed ip on the tenant network
function get_network_ip()
{
    if [ "x${ROUTED_TENANT_NETWORKS}" == "xyes" ]; then
        ## Doesn't matter since the VM will be bridging traffic and not routing
        echo ""
    else
        echo ",v4-fixed-ip=$(get_network_ip_address $1 $2 $3)"
    fi
}

## Retrieve the subnet id for a subnet name
function get_subnet_id()
{
    local NAME=$1
    echo $(openstack ${REGION_OPTION} subnet show ${NAME} -c id -f value 2>/dev/null)
}

## Retrieve the qos id for a qos name
function get_qos_id()
{
    local NAME=$1
    echo $(openstack ${REGION_OPTION} qos show ${NAME} -c id -f value 2>/dev/null)
}

## Retrieve the flavor id for a flavor name
function get_flavor_id()
{
    local NAME=$1
    echo $(nova ${REGION_OPTION} flavor-show ${NAME} 2>/dev/null | grep "| id" | awk '{print $4}')
}

## Retrieve a specific neutron quota value for a tenant
function get_neutron_quota()
{
    local TENANTID=$1
    local QUOTA=$2

    echo $(openstack ${REGION_OPTION} quota show ${TENANTID} -c ${QUOTA} -f value 2>/dev/null)
}

## Retrieve the hosts ip address of managment network
function get_mgmt_ip()
{
    local ID=$1
    echo $(system host-show ${ID} 2>/dev/null | grep "mgmt_ip" | awk '{print $4}')
}

## Retrieve the numa node flavor modifier for a given tenant
function get_flavor_modifier()
{
    local TENANTNUM=$1
    local VMCOUNTER=$2

    if [ "${TENANTNUM}" -gt ${#TENANTNODES[@]} ]; then
        echo ""
    elif [ "${TENANTNODES[${TENANTNUM}]}" == "split" ]; then
	local NODE=$(($((VMCOUNTER-1)) % ${NUMA_NODE_COUNT}))
	echo "node${NODE}"
    elif [ ! -z "${TENANTNODES[${TENANTNUM}]}" ]; then
        echo "${TENANTNODES[${TENANTNUM}]}"
    else
        echo ""
    fi

    return 0
}

## Retrieve the network id of the network to be used between two tenant VM
## instances.  If SHARED_TENANT_NETWORKS is set to "yes" then it is assumed
## that only a single VM is running and instead of using one of the actual
## internal networks the VM should use the other VM's tenant network to return
## traffic to ixia.
#
function get_internal_network_id()
{
    local TENANTNUM=$1
    local NETNUMBER=$2
    local VLANID=$3
    local OTHER_TENANTNET="${TENANTS[$((1 - ${TENANTNUM}))]}-net"
    local NET=0

    if [ "x${SHARED_TENANT_NETWORKS}" == "xyes" ]; then
        INTERNALNETID=$(get_network_id ${OTHER_TENANTNET}${NETNUMBER})
    else
        if [ "x${REUSE_NETWORKS}" != "xyes" ]; then
            NET=$((NETNUMBER / ${MAXVLANS}))

            INTERNALNETNAME=${INTERNALNET}${NET}
            if [ ${VLANID} -ne 0 ]; then
                INTERNALNETNAME=${INTERNALNET}${NET}-${VLANID}
            fi
        fi
        INTERNALNETID=$(get_network_id ${INTERNALNETNAME})
    fi

    echo ${INTERNALNETID}
    return 0
}

function get_internal_network_name()
{
    local TENANTNUM=$1
    local NETNUMBER=$2
    local OTHER_TENANTNET="${TENANTS[$((1 - ${TENANTNUM}))]}-net"
    local NET=0

    if [ "x${SHARED_TENANT_NETWORKS}" == "xyes" ]; then
        echo ${OTHER_TENANTNET}${NETNUMBER}
    else
        if [ "x${REUSE_NETWORKS}" != "xyes" ]; then
            NET=$((NETNUMBER / ${MAXVLANS}))
        fi
        echo ${INTERNALNET}${NET}
    fi

    return 0
}


## Retrieve the value of a prefixed variable name.  If a variable named
## ${PREFIX}_${NAME} does not exist then a variable with DEFAULT_${NAME} is
## used.
##
function get_variable()
{
    local PREFIX=$1
    local NAME=$2

    ## No specific AEMODE for this interface, try the type-specific value
    local VARNAME=${PREFIX^^}_${NAME^^}
    if [ -z ${!VARNAME+x} ]; then
        ## No type-specific value, use the global default
        VARNAME=DEFAULT_${NAME^^}
        if [ -z ${!VARNAME+x} ]; then
            echo "Missing variable ${VARNAME}"
            exit 2
        fi
        VALUE=${!VARNAME}
    else
        VALUE=${!VARNAME}
    fi

    echo $VALUE
}


## Retrieve the value of a worker node overridden variable.  First the
## variable ${COMPUTE0_VARNAME} is checked and if no variable exists then
## ${VARNAME} is returned.  If ${VARNAME} also does not exist then an empty
## value is returned.
##
function get_node_variable()
{
    local NODE=${1/-/}
    local VARNAME=${NODE^^}_$2

    if [ -z "${!VARNAME+x}" ]; then
        # There is no node specific variable available use the default
        VARNAME=$2
    fi

    if [ -z "${!VARNAME+x}" ]; then
        # There is no variable with the requested name so return an empty
        # string
        echo ""
    else
        # Dereference the variable name and echo its' contents
        echo ${!VARNAME}
    fi

    return 0
}

## Generates the neutron provider args for an internal network
function get_internal_provider_network()
{
    DATA=(${INTERNALPNET//|/ })
    local PNET_TYPE=${DATA[0]}
    local PNET_NAME=group${GROUPNO}-${DATA[1]}
    if [ "${VSWITCH_TYPE}" == "avs" ]; then
        echo "--provider-network-type=${PNET_TYPE} --provider-physical-network=${PNET_NAME}"
    elif [ ${PNET_TYPE} == 'vxlan' ]; then
        echo "--provider-network-type=${PNET_TYPE}"
    else
        echo "--provider-network-type=${PNET_TYPE} --provider-physical-network=${PNET_NAME}"
    fi
}

## Generates the neutron provider args for the external network
function get_external_provider_network()
{
    DATA=(${EXTERNALPNET//|/ })
    local PNET_TYPE=${DATA[0]}
    local PNET_NAME=group${GROUPNO}-${DATA[1]}
    local SEGMENT_ID=${DATA[2]}
    local PNET_ARGS="--provider-network-type=${PNET_TYPE} --provider-physical-network=${PNET_NAME}"

    if [ "${VSWITCH_TYPE}" == "avs" ]; then
        PNET_ARGS="--provider-network-type=${PNET_TYPE} --provider-physical-network=${PNET_NAME}"
    elif [ ${PNET_TYPE} == 'vxlan' ]; then
        PNET_ARGS="--provider-network-type=${PNET_TYPE}"
    fi
    # Skip setting segmentation ID if EXTERNALPNET SEGMENT_ID is none, or VSWITCH_TYPE is avs
    # in the case of VSWITCH_TYPE=="avs", this can be reenabled once a bug with
    # allocate_fully_specified_segment is fixed.
    if [ "${VSWITCH_TYPE}" == "avs" ]; then :
    elif [ ${SEGMENT_ID} != 'none' ]; then
        PNET_ARGS="${PNET_ARGS} --provider-segment=${SEGMENT_ID}"
    fi

    echo ${PNET_ARGS}
}



## Rudimentary check to determine if an address is IPv4
##
function is_ipv4()
{
    local VALUE=$1

    [[ ${VALUE} =~ ^[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}.[0-9]{1,3}$ ]]
    if [ $? -eq 0 ]; then
        return 1
    else
        return 0
    fi
}

## Derive the guest NIC device type based on the VM type
function get_guest_nic_device()
{
    local VMTYPE=$1

    if [ "$VMTYPE" == "vswitch" ]; then
	NIC_DEVICE="${PCI_VENDOR_VIRTIO}:${PCI_DEVICE_MEMORY}:${PCI_SUBDEVICE_AVP}"
    elif [ "$VMTYPE" == "vhost" ]; then
	NIC_DEVICE="${PCI_VENDOR_VIRTIO}:${PCI_DEVICE_VIRTIO}:${PCI_SUBDEVICE_NET}"
    else
	NIC_DEVICE=""
    fi

    echo "${NIC_DEVICE}"
    return 0;
}

## Determine whether one of the setup stages has already completed
function is_stage_complete()
{
    local STAGE=$1
    local NODE=${2:-""}
    local FILE=""

    if [ "${FORCE}" == "no" ]; then
        if [ -z "${NODE}" ]; then
            FILE=${GROUP_STATUS}.${STAGE}
        else
            FILE=${GROUP_STATUS}.${NODE}.${STAGE}
        fi
        if [ -f ${FILE} ]; then
            return 0
        fi
    fi

    return 1
}

## Mark a stage as complete
function stage_complete()
{
    local STAGE=$1
    local NODE=${2:-""}
    local FILE=""

    if [ -z "${NODE}" ]; then
        FILE=${GROUP_STATUS}.${STAGE}
    else
        FILE=${GROUP_STATUS}.${NODE}.${STAGE}
    fi

    touch ${FILE}
    log "Stage complete: ${STAGE}"

    return 0
}

## Check for prerequisite files
##
function check_required_files()
{
    mkdir -p ${USERDATA_DIR}
    mkdir -p ${BOOTDIR}
    mkdir -p ${IMAGE_DIR}

    if [ ! -f ${OPENRC} ]; then
        echo "Nova credential file is missing: ${OPENRC}"
        return 1
    fi

    if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xsubcloud" ]; then
        if [ ! -f ${IMAGE_DIR}/${DPDK_IMAGE}.img ]; then
            echo "CGCS guest image is missing: ${IMAGE_DIR}/${DPDK_IMAGE}.img"
            return 1
        fi

        if [ ! -f ${IMAGE_DIR}/${AVP_IMAGE}.img ]; then
            echo "CGCS guest image is missing: ${IMAGE_DIR}/${AVP_IMAGE}.img"
            return 1
        fi
                
        if [ ! -f ${IMAGE_DIR}/${VIRTIO_IMAGE}.img ]; then
            echo "CGCS guest image is missing: ${IMAGE_DIR}/${VIRTIO_IMAGE}.img"
            return 1
        fi

        if [ ! -f ${IMAGE_DIR}/${SRIOV_IMAGE}.img ]; then
            echo "CGCS guest image is missing: ${IMAGE_DIR}/${SRIOV_IMAGE}.img"
            return 1
        fi

        if [ ! -f ${IMAGE_DIR}/${PCIPT_IMAGE}.img ]; then
            echo "CGCS guest image is missing: ${IMAGE_DIR}/${PCIPT_IMAGE}.img"
            return 1
        fi
    fi
    if [ ${GROUPNO} -eq 0 ]; then
        if [ ! -L ${DEFAULT_BOOTDIR} ]; then
            ln -s ${BOOTDIR} ${DEFAULT_BOOTDIR}
        fi
    fi

    return 0
}

## Increment an IP address by an arbitrary amount.  There is no elegant way of
## doing this in bash, that handles both ipv4 and ipv6, without installing
## other packages so python is used.
function ip_incr()
{
    local IPADDRESS=$1
    local VALUE=$2

    python -c "import netaddr;print netaddr.IPAddress('${IPADDRESS}')+${VALUE}"
}

## Add tenants and users
function add_tenants()
{
    local TENANTID=0

    if is_stage_complete "tenants"; then
        info "Skipping tenant configuration; already done"
        return 0
    fi

    info "Adding tenants"
    check_url_status ${K8S_URL}
    RET=$?
    if [ ${RET} -ne 0 ]; then
        echo "Failed to connecto to ${K8S_URL}, ret=${RET}"
        exit ${RET}
    fi

    for TENANT in ${TENANTS[@]}; do
        ## Create the project if it does not exist
        TENANTID=$(get_tenant_id ${TENANT})
        if [ -z "${TENANTID}" ]; then
            log_command "openstack project create \
--domain ${OPENSTACK_PROJECT_DOMAIN} --description ${TENANT} ${TENANT}"
        fi

        ## Create the user if it does not exist
        USERID=$(get_user_id ${TENANT})
        if [ -z "${USERID}" ]; then
            log_command "openstack user create \
--password ${DEFAULT_OPENSTACK_PASSWORD} --domain ${OPENSTACK_USER_DOMAIN} --project ${TENANT} \
--project-domain ${OPENSTACK_PROJECT_DOMAIN} \
--email ${TENANT}@noreply.com ${TENANT}"
        fi

        ## Ensure tenant user is a member of the project
        ROLES=$(get_user_roles ${TENANT} ${TENANT})
        if [[ ! $ROLES =~ ${MEMBER_ROLE} ]]; then
            log_command "openstack role add --project ${TENANT} \
--project-domain ${OPENSTACK_PROJECT_DOMAIN} --user ${TENANT} \
--user-domain ${OPENSTACK_USER_DOMAIN} ${MEMBER_ROLE}"
        fi

        ## Add the admin user to each group/project so that all projects can be
        ## accessed from Horizon without needing to logout/login again.
        ROLES=$(get_user_roles ${TENANT} ${ADMIN_USER})
        if [[ ! $ROLES =~ ${MEMBER_ROLE} ]]; then
            log_command "openstack role add --project ${TENANT} \
--project-domain ${OPENSTACK_PROJECT_DOMAIN} --user ${ADMIN_USER} \
--user-domain ${OPENSTACK_USER_DOMAIN} ${MEMBER_ROLE}"
        fi
    done

    stage_complete "tenants"

    return 0
}

## Create credential files for tenants
##
function create_credentials()
{
    local TENANT=""
    local ADMIN_URL="35357"
    local PUBLIC_URL="5000"
    local K8S_URL="http://keystone.openstack.svc.cluster.local/v3"

    if is_stage_complete "credentials"; then
        info "Skipping credential configuration; already done"
        return 0
    fi

    info "Adding tenant credentials"

    for TENANT in ${TENANTS[@]}; do
        cp ${OPENRC} ${HOME}/openrc.${TENANT}
        sed -i -e "s#admin#${TENANT}#g" ${HOME}/openrc.${TENANT}
        sed -i -e "s#\(OS_PASSWORD\)=.*#\1=${DEFAULT_OPENSTACK_PASSWORD}#g" ${HOME}/openrc.${TENANT}
        sed -i -e "s#${ADMIN_URL}#${PUBLIC_URL}#g" ${HOME}/openrc.${TENANT}
	if [ "$K8S_ENABLED" == "yes" ]; then
	    sed -i -e "s#\(OS_AUTH_URL\)=.*#\1=${K8S_URL}#g" ${HOME}/openrc.${TENANT}
	fi
    done

    if [ "$K8S_ENABLED" == "yes" ]; then
        cp ${OPENRC} ${HOME}/openrc.admin
	sed -i -e "s#\(OS_AUTH_URL\)=.*#\1=${K8S_URL}#g" ${HOME}/openrc.admin
    fi
    
    stage_complete "credentials"

    return 0
}


function set_cinder_quotas()
{
    if is_stage_complete "quotas_cinder"; then
        info "Skipping cinder quota configuration; already done"
        return 0
    fi

    info "Adding cinder quotas"
    unset OS_AUTH_URL
    export OS_AUTH_URL=${K8S_URL}
    for TENANT in ${TENANTS[@]}; do
        TENANTID=$(get_tenant_id ${TENANT})
        log_command "openstack ${REGION_OPTION} quota set ${TENANTID} \
--volumes ${VOLUME_QUOTA} \
--snapshots ${SNAPSHOT_QUOTA}"
    done

    stage_complete "quotas_cinder"
}

## Adjust quotas
##
function set_quotas()
{
    local SQUOTA=0
    local NQUOTA=0
    local PQUOTA=0
    local RAMPARAM=""

    if is_stage_complete "quotas"; then
        info "Skipping quota configuration; already done"
        return 0
    fi

    info "Adding quotas"

    ## Set the Admin quotas.
    NQUOTA=$(get_neutron_quota ${ADMINID} "network")
    if [ "x${NQUOTA}" != "x${ADMIN_NETWORK_QUOTA}" -a ${GROUPNO} -eq 0 ]; then
        log_command "openstack ${REGION_OPTION} quota set ${ADMINID} --networks ${ADMIN_NETWORK_QUOTA}"
    fi
    SQUOTA=$(get_neutron_quota ${ADMINID} "subnet")
    if [ "x${SQUOTA}" != "x${ADMIN_SUBNET_QUOTA}" -a ${GROUPNO} -eq 0 ]; then
        log_command "openstack ${REGION_OPTION} quota set ${ADMINID} --subnets ${ADMIN_SUBNET_QUOTA}"
    fi
    PQUOTA=$(get_neutron_quota ${ADMINID} "port")
    if [ "x${PQUOTA}" != "x${ADMIN_PORT_QUOTA}" -a ${GROUPNO} -eq 0 ]; then
        log_command "openstack ${REGION_OPTION} quota set ${ADMINID} --ports ${ADMIN_PORT_QUOTA}"
    fi

    # Only set RAM quota if value is specified
    if [ ! -z "${RAM_QUOTA}" ]; then
        RAMPARAM="--ram ${RAM_QUOTA}"
    fi

    for TENANT in ${TENANTS[@]}; do
        TENANTID=$(get_tenant_id ${TENANT})
        NQUOTA=$(get_neutron_quota ${TENANTID} "network")
        SQUOTA=$(get_neutron_quota ${TENANTID} "subnet")
        PQUOTA=$(get_neutron_quota ${TENANTID} "port")
        ## Setup neutron quota (if necessary)
        if [ "x${NQUOTA}" != "x${NETWORK_QUOTA}" -o "x${SQUOTA}" != "x${SUBNET_QUOTA}" -o "x${PQUOTA}" != "x${PORT_QUOTA}" ]; then
            log_command "openstack ${REGION_OPTION} quota set ${TENANTID} \
--subnets ${SUBNET_QUOTA} \
--networks ${NETWORK_QUOTA} \
--ports ${PORT_QUOTA} \
--floating-ips ${FLOATING_IP_QUOTA}"
        fi

        ## Setup nova quotas
        log_command "nova ${REGION_OPTION} quota-update ${TENANTID} \
--instances ${INSTANCE_QUOTA} \
--cores ${CORE_QUOTA} \
${RAMPARAM}"

    done

    ## Prevent the admin from launching VMs
    log_command "nova ${REGION_OPTION} quota-update ${ADMINID} --instances 0 --cores 0"
    log_command "openstack ${REGION_OPTION} quota set ${ADMINID} --floating-ips 0"

    stage_complete "quotas"
}


## Retrieve the network segment range id for a segment range name
function get_network_segment_range_id()
{
    local RANGE_NAME=$1
    echo $(openstack ${REGION_OPTION} network segment range show ${RANGE_NAME} -c id -f value 2>/dev/null)
}

## Adds a set of internal segments ranges alternating between VXLAN_GROUP and
## VXLAN_PORT values according with VXLAN_INTERNAL_STEP segments in each
## range.  This is to facilitate having different group addresses and
## potentially each group could be either IPv4 or IPv6
##
function setup_vxlan_network_segment_ranges_varied()
{
    local INDEX=$1
    local NAME=$2
    local OWNER_ARGS="$3"
    local RANGES=(${4//,/ })
    local GROUPS_VARNAME=$5
    local PORTS_VARNAME=$6
    local GROUP_IDX=0
    local PORT_IDX=0

    local MCAST_GROUPS=(${!GROUPS_VARNAME})
    local UDP_PORTS=(${!PORTS_VARNAME})

    VALUES=${MCAST_GROUPS[@]}
    debug "vxlan provider ranges with ${#MCAST_GROUPS[@]} group attributes: ${VALUES}"
    VALUES=${UDP_PORTS[@]}
    debug "vxlan provider ranges with ${#UDP_PORTS[@]} attributes: ${VALUES}"

    local COUNT=0
    for I in ${!RANGES[@]}; do
        local RANGE=${RANGES[${I}]}
        RANGE=(${RANGE/-/ })

        ## Start at the beginning for each new range
        GROUP_IDX=0
        PORT_IDX=0

        for J in $(seq ${RANGE[0]} ${VXLAN_INTERNAL_STEP} ${RANGE[1]}); do
            local RANGE_NAME=${NAME}-r${INDEX}-${COUNT}

            RANGEID=$(get_network_segment_range_id ${RANGE_NAME})
            if [ ! -z "${RANGEID}" ]; then
                ## already exists
                continue
            fi

            END=$((J+${VXLAN_INTERNAL_STEP}-1))
            END=$((${END} < ${RANGE[1]} ? ${END} : ${RANGE[1]}))

            log_command "openstack ${REGION_OPTION} network segment range create ${RANGE_NAME} --network-type vxlan --minimum ${J} --maximum ${END} ${OWNER_ARGS}"

            # log_command "openstack ${REGION_OPTION} providernet range create ${NAME} --name ${RANGE_NAME} ${OWNER_ARGS} --range ${J}-${END} ${VXLAN_ARGS}"

            GROUP_IDX=$(((GROUP_IDX + 1) % ${#MCAST_GROUPS[@]}))
            PORT_IDX=$(((PORT_IDX + 1) % ${#UDP_PORTS[@]}))

            COUNT=$((COUNT+1))
        done
    done

    return 0
}

## Sets up a single VXLAN provider network with range details and VXLAN
## attributes.  The GROUPS and PORTS arguments are optional and if not
## specified will be taken from the global variable VXLAN_GROUPS or
## VXLAN_PORTS.
##
function setup_vxlan_network_segment_ranges()
{
    local INDEX=$1
    local NAME=group${GROUPNO}-$2
    local MTU=$3
    local RANGES=$4
    local OWNER=$5
    set +u
    local MCAST_GROUPS=(${6//,/ })
    local UDP_PORTS=(${7//,/ })
    local TTL=$8
    set -u

    OWNER_ARGS="--shared"
    if [ "${OWNER}" != "shared" ]; then
        OWNER_ARGS="--private --project $(get_tenant_id ${OWNER})"
    fi

    if [ -z "${MCAST_GROUPS+x}" ]; then
        ## Use global defaults
        MCAST_GROUPS=(${VXLAN_GROUPS})
    fi

    if [ -z "${UDP_PORTS+x}" ]; then
        ## Use global defaults
        UDP_PORTS=(${VXLAN_PORTS})
    fi

    if [ -z "${TTL}" ]; then
        ## Use global default
        TTL=${VXLAN_TTL}
    fi

    if [ ${#MCAST_GROUPS[@]} -gt 1 -o ${#UDP_PORTS[@]} -gt 1 ]; then
        ## Setup smaller ranges with varying groups and ports
        setup_vxlan_network_segment_ranges_varied ${INDEX} ${NAME} "${OWNER_ARGS}" ${RANGES} MCAST_GROUPS[@] UDP_PORTS[@]
    else
        ## Setup just a single set of ranges each with the same VXLAN attributes
        VALUES=${MCAST_GROUPS[@]}
        debug "vxlan provider ranges with group attributes: ${VALUES}"
        VALUES=${UDP_PORTS[@]}
        debug "vxlan provider ranges with attributes: ${VALUES}"

        RANGES=(${RANGES//,/ })
        for I in ${!RANGES[@]}; do
            local RANGE=${RANGES[${I}]}
            local RANGE_MIN=$(echo "${RANGE}" | cut -f1 -d-)
            local RANGE_MAX=$(echo "${RANGE}" | cut -f2 -d-)
            local RANGE_NAME=${NAME}-r${INDEX}-${I}

            RANGEID=$(get_network_segment_range_id ${RANGE_NAME})
            if [ ! -z "${RANGEID}" ]; then
                ## already exists
                return 0
            fi

            log_command "openstack ${REGION_OPTION} network segment range create ${RANGE_NAME} --network-type vxlan --minimum ${RANGE_MIN} --maximum ${RANGE_MAX} ${OWNER_ARGS}"

        done
    fi

    return 0
}

## Sets up a single VLAN data network with range details
##
function setup_vlan_network_segment_ranges()
{
    local INDEX=$1
    local NAME=group${GROUPNO}-$2
    local MTU=$3
    local RANGES=$4
    local OWNER=$5

    OWNER_ARGS="--shared"
    if [ "${OWNER}" != "shared" ]; then
        OWNER_ARGS="--private --project $(get_tenant_id ${OWNER})"
    fi

    RANGES=(${RANGES//,/ })
    for I in ${!RANGES[@]}; do
        local RANGE=${RANGES[${I}]}
        local RANGE_NAME=${NAME}-r${INDEX}-${I}
        local RANGE_MIN=$(echo "${RANGE}" | cut -f1 -d-)
        local RANGE_MAX=$(echo "${RANGE}" | cut -f2 -d-)

        RANGEID=$(get_network_segment_range_id ${RANGE_NAME})
        if [ ! -z "${RANGEID}" ]; then
            ## already exists
            return 0
        fi

        log_command "openstack ${REGION_OPTION} network segment range create ${RANGE_NAME} --network-type vlan --physical-network ${NAME} --minimum ${RANGE_MIN} --maximum ${RANGE_MAX} ${OWNER_ARGS}"

    done

    return 0
}

## Loops over all PROVIDERNETS entries and creates each
## network segment range according to its attributes.
##
function add_network_segment_ranges()
{
    local PNETS=(${PROVIDERNETS})

    source ${OPENRC}
    unset OS_AUTH_URL
    export OS_AUTH_URL=${K8S_URL}


    if is_stage_complete "network_segment_ranges"; then
        info "Skipping network segment ranges; already done"
        return 0
    fi

    info "Adding network segment ranges"

    for IFINDEX in ${!PNETS[@]}; do
        ENTRY=${PNETS[${IFINDEX}]}
        DATA=(${ENTRY//|/ })
        TYPE=${DATA[0]}

        debug "setting up network segment ranges (${IFINDEX}): ${ENTRY}"

        ## Remove the type from the array
        unset DATA[0]
        DATA=(${DATA[@]})

        if [ "${TYPE}" == "vxlan" ]; then
            setup_vxlan_network_segment_ranges ${IFINDEX} "${DATA[@]}"

        elif [ "${TYPE}" == "vlan" ]; then
            setup_vlan_network_segment_ranges ${IFINDEX} "${DATA[@]}"

        elif [ "${TYPE}" == "flat" ]; then
            continue

        else
            echo "unsupported data network type: ${TYPE}"
            return 1
        fi

        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to setup network segment range (${IFINDEX}): ${ENTRY}"
            return ${RET}
        fi
    done

    stage_complete "network_segment_ranges"

    return 0
}

## Setup network qos policies
##
function add_qos_policies()
{
    local TENANTID=""
    local MGMTQOS=""
    local ID=""

    source ${OPENRC}
    if [ "$K8S_ENABLED" == "yes" ]; then
        unset OS_AUTH_URL
        export OS_AUTH_URL=${K8S_URL}
    fi

    if is_stage_complete "qos"; then
        info "Skipping QoS configuration; already done"
        return 0
    fi

    info "Adding network qos policies"

    ID=$(get_qos_id ${EXTERNALQOS})
    if [ -z "${ID}" ]; then
        log_command "openstack ${REGION_OPTION} qos create --name ${EXTERNALQOS} --description \"External Network Policy\" --scheduler weight=${EXTERNALQOSWEIGHT}"
    fi

    ID=$(get_qos_id ${INTERNALQOS})
    if [ -z "${ID}" ]; then
        log_command "openstack ${REGION_OPTION} qos create --name ${INTERNALQOS} --description \"Internal Network Policy\" --scheduler weight=${INTERNALQOSWEIGHT}"
    fi

    for TENANT in ${TENANTS[@]}; do
        TENANTID=$(get_tenant_id ${TENANT})
        MGMTQOS="${TENANT}-mgmt-qos"
        ID=$(get_qos_id ${MGMTQOS})
        if [ -z "${ID}" ]; then
            log_command "openstack ${REGION_OPTION} qos create --name ${MGMTQOS} --description \"${TENANT} Management Network Policy\" --project ${TENANTID} --scheduler weight=${MGMTQOSWEIGHT}"
        fi
    done

    stage_complete "qos"

    return 0
}

## Setup common shared networking resources
##
function setup_internal_networks()
{
    local TRANSPARENT_ARGS=""
    local TRANSPARENT_INTERNAL_ARGS=""
    local DHCPARGS=""
    local VLANARGS=""
    local PORT_SECURITY_ARGS=""
    local QOS_ARGS=""
    local VLANID=0
    local LIMIT=0
    local COUNT=0
    local NET=0
    local ID=""

    if is_stage_complete "internal_networks"; then
        info "Skipping shared internal networks configuration; already done"
        return 0
    fi

    if [ "$K8S_ENABLED" == "yes" ]; then
        unset OS_AUTH_URL
        export OS_AUTH_URL=${K8S_URL}
    fi

    info "Adding shared internal networks"

    if [ "x${INTERNALNET_DHCP}" != "xyes" ]; then
        DHCPARGS="--no-dhcp"
    fi

    if [ "${NEUTRON_PORT_SECURITY}" == "True" ]; then
	    PORT_SECURITY_ARGS="--enable-port-security"
    fi

    if [ "${NEUTRON_PORT_SECURITY}" == "False" ]; then
	    PORT_SECURITY_ARGS="--disable-port-security"
    fi

    if [ "${VSWITCH_TYPE}" == "avs" ]; then
        QOS_ARGS="--wrs-tm:qos $(get_qos_id ${EXTERNALQOS})"
    fi

    ## Setup the shared external network
    EXTERNAL_PROVIDER=$(get_external_provider_network)
    ID=$(get_network_id ${EXTERNALNET})
    if [ -z "${ID}" ]; then
        log_command "openstack ${REGION_OPTION} network create --project ${ADMINID} ${EXTERNAL_PROVIDER} --share --external ${EXTERNALNET} ${QOS_ARGS} ${PORT_SECURITY_ARGS}"
    fi

    ID=$(get_subnet_id ${EXTERNALSUBNET})
    if [ -z "${ID}" ]; then
        log_command "openstack ${REGION_OPTION} subnet create --project ${ADMINID} ${EXTERNALSUBNET} --gateway ${EXTERNALGWIP} --no-dhcp --network ${EXTERNALNET} --subnet-range ${EXTERNALCIDR} --ip-version ${EXTIPVERSION}"
    fi

    if [ "${SHARED_TENANT_NETWORKS}" == "yes" -o "${EXTRA_NICS}" != "yes" ]; then
        ## Internal networks are not required since VM instances will be
        ## directly connected to tenant data networks see comment describing
        ## the use of this variable.
        stage_complete "internal_networks"
        return 0
    fi

    LIMIT=$((NETCOUNT - 1))
    if [ "x${REUSE_NETWORKS}" == "xyes" ]; then
        ## Only create a single internal network
        LIMIT=1
    fi

    if [ "${FIRSTVLANID}" -ne "0" ]; then
        INTERNALNETNAME=${INTERNALNET}${NET}
        INTERNALSUBNETNAME=${INTERNALSUBNET}${NET}
            INTERNALSUBNETNAME=${INTERNALSUBNET}${NET}-${VLANID}

        INTERNALNETID=$(get_network_id ${INTERNALNETNAME})
        if [ -z "${INTERNALNETID}" ]; then
            INTERNAL_PROVIDER=$(get_internal_provider_network 0)
            log_command "openstack ${REGION_OPTION} network create --project ${ADMINID} ${INTERNAL_PROVIDER} --share ${INTERNALNETNAME} ${QOS_ARGS} ${TRANSPARENT_INTERNAL_ARGS}"
        fi
    fi

    ## Setup the shared internal network(s)
    local QOS_ARGS=""
    if [ "${VSWITCH_TYPE}" == "avs" ]; then
        QOS_ARGS="--wrs-tm:qos $(get_qos_id ${INTERNALQOS})"
    fi
    for I in $(seq 0 ${LIMIT}); do
        NET=$((I / ${MAXVLANS}))
        VLANID=$(((I % ${MAXVLANS}) + ${FIRSTVLANID}))

        INTERNALNETNAME=${INTERNALNET}${NET}
        INTERNALSUBNETNAME=${INTERNALSUBNET}${NET}
        if [ ${VLANID} -ne 0 ]; then
            INTERNALNETNAME=${INTERNALNET}${NET}-${VLANID}
            INTERNALSUBNETNAME=${INTERNALSUBNET}${NET}-${VLANID}
        fi

        INTERNALNETID=$(get_network_id ${INTERNALNETNAME})
        if [ -z "${INTERNALNETID}" ]; then
            INTERNAL_PROVIDER=$(get_internal_provider_network ${I})
            log_command "openstack ${REGION_OPTION} network create --project ${ADMINID} ${INTERNAL_PROVIDER} --share ${INTERNALNETNAME} ${QOS_ARGS} ${TRANSPARENT_INTERNAL_ARGS}"
        fi

        SUBNET=10.${I}.${VLANID}
        SUBNETCIDR=${SUBNET}.0/24

        # The VM user data is setup to statically assign addresses to each VM
        # instance so we need to make sure that any dynamic addresses (i.e.,
        # DHCP port addresses, Router addresses) are not in conflict with any
        # addresses that are chosen by this script.  WARNING: the IP addresses
        # set in the user data will not correspond to the IP addresses selected
        # by neutron.  This used to be the case but in Newton we can no longer
        # set the fixed_ip when booting on the internal network because it is
        # shared and owned by the admin.  We would need to create the port
        # ahead of time, let the system pick an address, and then set the user
        # data accordingly.  That's too complicated to do for what we need.
        POOLARGS="--allocation-pool start=${SUBNET}.128,end=${SUBNET}.254"

        ID=$(get_subnet_id ${INTERNALSUBNETNAME})
        if [ -z "${ID}" ]; then
            log_command "openstack ${REGION_OPTION} subnet create --project ${ADMINID} ${INTERNALSUBNETNAME} ${DHCPARGS} ${POOLARGS} --gateway none --network ${INTERNALNETNAME} --subnet-range ${SUBNETCIDR}"
        fi
        COUNT=$((COUNT + 1))
    done

    stage_complete "internal_networks"

    return 0
}


## Setup a management router
##
function setup_management_router()
{
    local TENANT=$1
    local NAME=$2
    local EXTERNAL_NETWORK=$3
    local DVR_ENABLED=$4
    local EXTERNAL_SNAT=$5
    local TENANTNUM=$6

    ID=$(get_router_id ${NAME})
    if [ -z "${ID}" ]; then
        log_command "openstack ${REGION_OPTION} router create ${NAME}"
    fi

    if [ "x${DVR_ENABLED}" == "xyes" ]; then
        ## Switch to admin context and update the router to be distributed
        source ${OPENRC}
        if [ "$K8S_ENABLED" == "yes" ]; then
            unset OS_AUTH_URL
            export OS_AUTH_URL=${K8S_URL}
        fi

        log_command "openstack ${REGION_OPTION} router set ${NAME} --disable"
        log_command "openstack ${REGION_OPTION} router set ${NAME} --distributed"
	log_command "openstack ${REGION_OPTION} router set ${NAME} --enable"
    fi

    source ${OPENRC}
    if [ "$K8S_ENABLED" == "yes" ]; then
        unset OS_AUTH_URL
        export OS_AUTH_URL=${K8S_URL}
    fi
    # In newton, neutron will allocate ip addresses non-sequentially so in
    # order for us to get predictable ip addresses for our router gateway
    # interfaces we must set them ourselves. We set it separately because
    # the CLI does not support setting a fixed ip when updating the
    # external_gateway_info dict.
    log_command "openstack ${REGION_OPTION} router set ${NAME} --external-gateway ${EXTERNAL_NETWORK} --fixed-ip ip-address=$(ip_incr ${EXTERNALGWIP} $((TENANTNUM+1)))"

    if [ "x${EXTERNAL_SNAT}" == "xno" ]; then
        ## Switch to admin context and update the router to disable SNAT
        log_command "openstack ${REGION_OPTION} router set ${NAME} --external-gateway ${EXTERNAL_NETWORK} --disable-snat"
    fi

    ## Switch back to tenant context
    source ${HOME}/openrc.${TENANT}

    return 0
}

## Setup a single management subnet
##
function setup_management_subnet()
{
    local TENANT=$1
    local NETWORK=$2
    local CIDR=$3
    local NAME=$4
    local ROUTER=$5
    local POOL=$6
    local PROVIDERARGS=""
    local DNSARGS=""
    local POOLARGS=""
    local IPARGS=""
    local OWNERARGS=""
    local ELEVATE_CREDENTIALS=""
    local RESTORE_CREDENTIALS=""

    ID=$(get_subnet_id ${NAME})
    if [ ! -z "${ID}" ]; then
        ## already exists
        return 0
    fi

    for NAMESERVER in ${DNSNAMESERVERS}; do
        DNSARGS="${DNSARGS} --dns-nameserver ${NAMESERVER}"
    done

    if [ ! -z "${POOL}" -a "${POOL}" != "none" ]; then
        POOLARRAY=(${POOL//-/ })
        POOLARGS="--allocation-pool start=${POOLARRAY[0]},end=${POOLARRAY[1]}"
    fi

    IPFIELDS=(${CIDR//\// })
    set +e
    is_ipv4 ${IPFIELDS[0]}
    IS_IPV4=$?
    set -e
    if [ ${IS_IPV4} -eq 1 ]; then
        IPARGS="--ip-version=4"
    else
        IPARGS="--ip-version=6 --ipv6-address-mode=${MGMTIPV6ADDRMODE} --ipv6-ra-mode=${MGMTIPV6ADDRMODE}"
    fi

    ${ELEVATE_CREDENTIALS}

    if [ "${OS_USERNAME}" == "admin" ]; then
        OWNERARGS="--project=$(get_tenant_id ${TENANT})"
    fi

    log_command "openstack ${REGION_OPTION} subnet create --network ${NETWORK} --subnet-range ${CIDR} ${NAME} ${OWNERARGS} ${DNSARGS} ${POOLARGS} ${IPARGS}"

    ${RESTORE_CREDENTIALS}

    log_command "openstack ${REGION_OPTION} router add subnet ${ROUTER} ${NAME}"

    return 0
}

## Setup management networks
##
function setup_management_networks()
{
    local TENANTNUM=0
    local TENANT=""
    local QOS_ARGS=""
    local ID=""

    if is_stage_complete "management_networks"; then
        info "Skipping management networks configuration; already done"
        return 0
    fi

    info "Adding tenant management networks"

    for TENANT in ${TENANTS[@]}; do
        local MGMTQOS="${TENANT}-mgmt-qos"
        local MGMTROUTER="${TENANT}-router"
        source ${HOME}/openrc.${TENANT}

        local EXTERNALNETID=$(get_network_id ${EXTERNALNET})
        if [ -z "${EXTERNALNETID}" ]; then
            echo "Unable to get external network ${EXTERNALNET} for tenant ${TENANT}"
            return 1
        fi

        if [ "${VSWITCH_TYPE}" == "avs" ]; then
            local QOSID=$(get_qos_id ${MGMTQOS})
            if [ -z "${QOSID}" ]; then
                echo "Unable to find QoS resource for ${MGMTQOS} for tenant ${TENANT}"
                return 1
            else
                QOS_ARGS="--wrs-tm:qos ${QOSID}"
            fi
        fi

        for I in $(seq 0 $((MGMTNETS-1))); do
            local MGMTNET=$(get_mgmt_network_name ${TENANT}-mgmt-net ${I})
            local ID=$(get_network_id ${MGMTNET})
            if [ -z "${ID}" ]; then
                log_command "openstack ${REGION_OPTION} network create ${MGMTNET} ${QOS_ARGS}"
            fi
        done

        setup_management_router ${TENANT} ${MGMTROUTER} ${EXTERNALNETID} ${MGMTDVR[${TENANTNUM}]} ${EXTERNALSNAT} ${TENANTNUM}
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Unable to setup mgmt router ${MGMTROUTER} for ${TENANT}"
            return ${RET}
        fi

        SUBNETS=${MGMTSUBNETS[${TENANTNUM}]}
        if [ -z "${SUBNETS}" ]; then
            echo "Unable to find any defined subnets for ${TENANT}"
            return 1
        fi

        TMPSUBNETS=(${SUBNETS//,/ })
        SUBNETS_PER_NETWORK=$((${#TMPSUBNETS[@]} / ${MGMTNETS}))
        REMAINDER=$((${#TMPSUBNETS[@]} % ${MGMTNETS}))
        if [ ${REMAINDER} -ne 0 ]; then
            echo "Number of subnets in SUBNETS must be a multiple of MGMTNETS=${MGMTNETS}"
            return 1
        fi

        COUNT=0
        DATA=(${SUBNETS//,/ })
        for SUBNET in ${DATA[@]}; do
            ARRAY=(${SUBNET//|/ })
            CIDR=${ARRAY[0]}
            set +u
            POOL=${ARRAY[1]}
            set -u

            ## Distribute the subnets evenly across the number of mgmt networks
            NETWORK=$(((COUNT / ${SUBNETS_PER_NETWORK}) % ${MGMTNETS}))
            local MGMTNET=$(get_mgmt_network_name ${TENANT}-mgmt-net ${NETWORK})
            local MGMTSUBNET="${TENANT}-mgmt${NETWORK}-subnet${COUNT}"
            setup_management_subnet ${TENANT} ${MGMTNET} ${CIDR} ${MGMTSUBNET} ${MGMTROUTER} "${POOL}"
            RET=$?
            if [ ${RET} -ne 0 ]; then
                echo "Unable to setup mgmt subnet ${MGMTNET} ${SUBNET} for tenant ${TENANT}"
                return ${RET}
            fi

            COUNT=$((COUNT+1))
        done

        TENANTNUM=$((TENANTNUM + 1))
    done

    stage_complete "management_networks"

    return 0
}

## Setup glance images
##
function setup_glance_images()
{
    local IMAGE=""
    local ID=""
    local CACHE_ARGS=""

    if is_stage_complete "glance"; then
        info "Skipping glance configuration; already done"
        return 0
    fi

    info "Adding shared VM images"

    test -d ${IMAGE_DIR} || mkdir ${IMAGE_DIR}

    ## The 5 images are likely the same but we allow for customization
    ## by checking all 5 variables.
    for IMAGE in ${DPDK_IMAGE} ${AVP_IMAGE} ${VIRTIO_IMAGE} ${SRIOV_IMAGE} ${PCIPT_IMAGE} ${VHOST_IMAGE}; do
        ID=$(get_glance_id ${IMAGE})
        if [ -z "${ID}" ]; then
            log_command "glance ${REGION_OPTION} image-create --name ${IMAGE} --visibility public \
--container-format bare --disk-format ${IMAGE_FORMAT} \
--file ${IMAGE_DIR}/${IMAGE}.img"
        fi
    done

    ## Parse APPS definitions for any additional images
    local APPS=($ALLAPPS)
    for INDEX in ${!APPS[@]}; do
        ENTRY=${APPS[${INDEX}]}
        DATA=(${ENTRY//|/ })
        NUMVMS=${DATA[0]}

        # Initial pass through params to see if cache_raw feature is set
        CACHE_ARGS=""
        for KEYVALUE in ${DATA[@]}; do
            KEYVAL=(${KEYVALUE//=/ })
            if [ "x${KEYVAL[0]}" == "xcache_raw" ]; then
               CACHE_ARGS="--cache-raw"
            fi
        done

        for KEYVALUE in ${DATA[@]}; do
            KEYVAL=(${KEYVALUE//=/ })
            if [ "x${KEYVAL[0]}" == "ximage" ]; then
                ID=$(get_glance_id ${KEYVAL[1]})
                if [ -z "${ID}" ]; then
                    log_command "glance ${REGION_OPTION} image-create --name ${KEYVAL[1]} --visibility public \
--container-format bare --disk-format raw \
--file ${IMAGE_DIR}/${KEYVAL[1]}.img"
                fi
            elif [ "x${KEYVAL[0]}" == "ximageqcow2" ]; then
                ID=$(get_glance_id ${KEYVAL[1]})
                if [ -z "${ID}" ]; then
                    log_command "glance ${REGION_OPTION} image-create --name ${KEYVAL[1]} --visibility public \
--container-format bare --disk-format qcow2 \
--file ${IMAGE_DIR}/${KEYVAL[1]}.qcow2 ${CACHE_ARGS}"
                fi
            fi
        done
    done

    # enable virtio multiqueue support if requested
    if [ ${VIRTIO_MULTIQUEUE} == "true" ]; then
	ID=$(get_glance_id ${VIRTIO_IMAGE})
        if [ -n "${ID}" ]; then
	    log_command "glance ${REGION_OPTION} image-update --property hw_vif_multiqueue_enabled=true $ID"
	fi
    fi

    stage_complete "glance"

    return 0
}

## Create a single cinder volume if it doesn't already exist
##
function create_cinder_volume()
{
    local IMAGE=$1
    local NAME=$2
    local SIZE=$3

    local GLANCE_ID=$(get_glance_id ${IMAGE})
    if [ -z "${GLANCE_ID}" ]; then
        echo "No glance image with name: ${IMAGE}"
        return 1
    fi

    ID=$(get_cinder_id "vol-${NAME}")
    if [ -z "${ID}" ]; then
        log_command "openstack volume ${REGION_OPTION} create --image ${GLANCE_ID} --size ${SIZE} vol-${NAME}"
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to create cinder volume 'vol-${NAME}'"
            return ${RET}
        fi

        # Wait up to one minute for the volume to be created
        log "Creating volume 'vol-${NAME}'"
        DELAY=0
        sleep 2
        while [ $DELAY -lt ${CINDER_TIMEOUT} ]; do
            STATUS=$(get_cinder_status "vol-${NAME}")
            if [ "${STATUS}" == "downloading" -o "${STATUS}" == "creating" ]; then
                DELAY=$((DELAY + 5))
                sleep 5
            elif [ "${STATUS}" == "available" ]; then
                log "Success"
                return 0
            else
                log "Failed"
                return 1
            fi
        done

        log "Volume creation timed out: 'vol-${NAME}'"
        return 1
    fi

    return 0
}

## Create a single cinder launch file
##
function create_cinder_launch_file()
{
    # Changed this to write the cinder commands to a file rather than creating at initialization
    local IMAGE=$1
    local NAME=$2
    local SIZE=$3
    local VOLWAIT=$4
    local FILE=${BOOTDIR}/vol_${NAME}.sh

    local GLANCE_ID=$(get_glance_id ${IMAGE})
    if [ -z "${GLANCE_ID}" ]; then
        echo "No glance image with name: ${IMAGE}"
        return 1
    fi

    cat << EOF > ${FILE}
#!/bin/bash
#
source ${HOME}/openrc.${TENANT}

VOLWAIT="${VOLWAIT}"

CINDER_ID=\$(openstack volume ${REGION_OPTION} list | grep "vol-${NAME} " | awk '{print \$2}')
if [ -z "\${CINDER_ID}" ]; then
    openstack volume ${REGION_OPTION} create --image ${GLANCE_ID} --size ${SIZE} vol-${NAME} 
    RET=\$?
    if [ \${RET} -ne 0 ]; then
        echo "Failed to create cinder volume 'vol-${NAME}'"
        exit
    fi

    if [ "x\${VOLWAIT}" == "xyes" ]; then
        # Wait up to one minute for the volume to be created
        echo "Creating volume 'vol-${NAME}'"
        DELAY=0
        while [ \$DELAY -lt ${CINDER_TIMEOUT} ]; do
            STATUS=\$(openstack volume ${REGION_OPTION} show vol-${NAME} 2>/dev/null | awk '{ if (\$2 == "status") {print \$4} }')
            if [ \${STATUS} == "downloading" -o \${STATUS} == "creating" ]; then
                DELAY=\$((DELAY + 5))
                sleep 5
            elif [ \${STATUS} == "available" ]; then
                echo "Success"
                exit
            else
                echo "Failed"
                exit
            fi
        done
        echo "Timed out waiting for volume"
    fi
fi

EOF
    chmod 755 ${FILE}

    return 0
}

## Setup cinder volumes/images
##
function setup_cinder_volumes()
{
    local TENANT=""
    local VMNAME=""
    local RET=0
    local MY_IMAGE=""
    local MY_DISK=""
    local VOLDELAY="no"
    local VOLWAIT="no"
    local VMCOUNTER=0
    local TENANTLIST=${TENANTS[@]}

    if is_stage_complete "cinder"; then
        info "Skipping volume configuration; already done"
        return 0
    fi

    info "Adding VM volumes"

    if [ "${SHARED_TENANT_NETWORKS}" == "yes" ]; then
        ## Don't bother generating cinder volumes for the second tenant since
        ## the system is configured to only support one tenant's VM instances
        ## at a time.
        TENANTLIST=${TENANTS[0]}
    fi

    for TENANT in ${TENANTLIST}; do
        source ${HOME}/openrc.${TENANT}

        LIST=$(openstack volume ${REGION_OPTION} list | grep -E "[0-9a-zA-Z]{8}-" | awk '{print $6}')
        declare -A VOLNAMES
        for N in ${LIST}; do
            VOLNAMES[$N]=1;
        done

        ## Parse APP definitions and create volumes for each APPTYPE
        for INDEX in ${!APPTYPES[@]}; do
            APPTYPE=${APPTYPES[${INDEX}]}
            VMTYPE=${VMTYPES[${INDEX}]}
            APP_VARNAME=${APPTYPE}APPS
            IMAGE_VARNAME=${APPTYPE}_IMAGE
            VMCOUNTER=1

            APPS=(${!APP_VARNAME})
            for INDEX in ${!APPS[@]}; do
                ENTRY=${APPS[${INDEX}]}
                DATA=(${ENTRY//|/ })
                NUMVMS=${DATA[0]}
                log "  Adding ${APPTYPE} volume(s) ${ENTRY}"

                MY_IMAGE=${!IMAGE_VARNAME}
                MY_DISK=${IMAGE_SIZE}
                MY_BOOT_SOURCE=${IMAGE_TYPE}
                VOLDELAY="no"
                VOLWAIT="no"
                for KEYVALUE in ${DATA[@]}; do
                    KEYVAL=(${KEYVALUE//=/ })
                    if [ "x${KEYVAL[0]}" == "ximage" -o "x${KEYVAL[0]}" == "ximageqcow2" ]; then
                        MY_IMAGE=${KEYVAL[1]}
                    elif [ "x${KEYVAL[0]}" == "xdisk" ]; then
                        MY_DISK=${KEYVAL[1]}
                    elif [ "x${KEYVAL[0]}" == "xvoldelay" ]; then
                        VOLDELAY="yes"
                    elif [ "x${KEYVAL[0]}" == "xglance" ]; then
                        MY_BOOT_SOURCE="glance"
                    elif [ "x${KEYVAL[0]}" == "xvolwait" ]; then
                        VOLWAIT="yes"
                    fi
                done

                for I in $(seq 1 ${NUMVMS}); do
                    # Create volume if not using glance and volume doesn't already exist
                    if [ "x${MY_BOOT_SOURCE}" != "xglance" ]; then
                        VMNAME="${TENANT}-${VMTYPE}${VMCOUNTER}"
                        if [ -z "${VOLNAMES[vol-${VMNAME}]+x}" ]; then
                            if [ "x${VOLDELAY}" != "xyes" ]; then
                                create_cinder_volume ${MY_IMAGE} ${VMNAME} ${MY_DISK}
                                RET=$?
                                if [ ${RET} -ne 0 ]; then
                                    return ${RET}
                                fi
                            fi
                            create_cinder_launch_file ${MY_IMAGE} ${VMNAME} ${MY_DISK} ${VOLWAIT}
                        fi
                    fi
                    VMCOUNTER=$((VMCOUNTER+1))
                done
            done
        done
    done

    stage_complete "cinder"

    source ${OPENRC}

    return 0
}

DEDICATED_CPUS="hw:cpu_policy=dedicated"
SHARED_CPUS="hw:cpu_policy=shared"
DPDK_CPU="hw:cpu_model=${DPDK_VCPUMODEL}"

if [ ${SHARED_PCPU} -ne 0 ]; then
    SHARED_VCPU="hw:wrs:shared_vcpu=0"
else
    SHARED_VCPU=""
fi

if [ ${LOW_LATENCY} == "yes" ]; then
    CPU_REALTIME="hw:cpu_realtime=yes"
    CPU_REALTIME_MASK="hw:cpu_realtime_mask=^0"
else
    CPU_REALTIME=""
    CPU_REALTIME_MASK=""
fi

## FIXME:  these are not ported yet
##HEARTBEAT_ENABLED="guest-heartbeat=true"
HEARTBEAT_ENABLED=""

function flavor_create()
{
    local NAME=$1
    local ID=$2
    local MEM=$3
    local DISK=$4
    local CPU=$5

    shift 5
    local USER_ARGS=$*
    local DEFAULT_ARGS="hw:mem_page_size=2048"

    local X=$(get_flavor_id ${NAME})
    
    if [ "$K8S_ENABLED" == "yes" ]; then
        unset OS_AUTH_URL
        export OS_AUTH_URL=${K8S_URL}
    fi

    if [ -z "${X}" ]; then
        log_command "nova ${REGION_OPTION} flavor-create ${NAME} ${ID} ${MEM} ${DISK} ${CPU}"
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to create flavor: ${NAME}"
            exit ${RET}
        fi

        log_command "nova ${REGION_OPTION} flavor-key ${NAME} set ${USER_ARGS} ${DEFAULT_ARGS}"
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to set ${NAME} extra specs: ${USER_ARGS} ${DEFAULT_ARGS}"
            exit ${RET}
        fi
    fi

    return 0
}

## Setup flavors
##
function setup_all_flavors()
{
    local FLAVORS=""
    local FLAVOR=""
    local HB_FLAVOR_SUFFIX=".hb"
    local HB_FLAVOR_ARGS="${DEDICATED_CPUS} ${HEARTBEAT_ENABLED}"
    local DPDK_FLAVOR_SUFFIX=".dpdk"
    local DPDK_FLAVOR_ARGS="${DEDICATED_CPUS} ${SHARED_VCPU} ${DPDK_CPU}"

    local ID=""

    ## Create custom flavors (pinned on any numa node)
    FLAVOR="small"
    flavor_create ${FLAVOR} auto 512 ${IMAGE_SIZE} 1 ${DEDICATED_CPUS}
    flavor_create ${FLAVOR}${HB_FLAVOR_SUFFIX} auto 512 ${IMAGE_SIZE} 1 ${HB_FLAVOR_ARGS}

    FLAVOR="medium"
    flavor_create ${FLAVOR} auto 1024 ${IMAGE_SIZE} 2 ${DEDICATED_CPUS}
    flavor_create ${FLAVOR}${HB_FLAVOR_SUFFIX} auto 1024 ${IMAGE_SIZE} 2 ${HB_FLAVOR_ARGS}
    flavor_create ${FLAVOR}${DPDK_FLAVOR_SUFFIX} auto 1024 ${IMAGE_SIZE} 2 ${DPDK_FLAVOR_ARGS}

    FLAVOR="large"
    flavor_create ${FLAVOR} auto 2048 ${IMAGE_SIZE} 3 ${DEDICATED_CPUS}
    flavor_create ${FLAVOR}${HB_FLAVOR_SUFFIX} auto 2048 ${IMAGE_SIZE} 3 ${HB_FLAVOR_ARGS}
    flavor_create ${FLAVOR}${DPDK_FLAVOR_SUFFIX} auto 2048 ${IMAGE_SIZE} 3 ${DPDK_FLAVOR_ARGS}

    FLAVOR="xlarge"
    flavor_create ${FLAVOR} auto 4096 ${IMAGE_SIZE} 3 ${DEDICATED_CPUS}
    flavor_create ${FLAVOR}${HB_FLAVOR_SUFFIX} auto 4096 ${IMAGE_SIZE} 3 ${HB_FLAVOR_ARGS}
    flavor_create ${FLAVOR}${DPDK_FLAVOR_SUFFIX} auto 4096 ${IMAGE_SIZE} 3 ${DPDK_FLAVOR_ARGS}

    ## Create custom flavors (not pinned to any cpu)
    FLAVOR="small.float"
    flavor_create ${FLAVOR} auto 512 ${IMAGE_SIZE} 1 ${SHARED_CPUS}
    flavor_create ${FLAVOR}${HB_FLAVOR_SUFFIX} auto 512 ${IMAGE_SIZE} 1 ${SHARED_CPUS} ${HEARTBEAT_ENABLED}

    FLAVOR="medium.float"
    flavor_create ${FLAVOR} auto 1024 ${IMAGE_SIZE} 2 ${SHARED_CPUS}
    flavor_create ${FLAVOR}${HB_FLAVOR_SUFFIX} auto 1024 ${IMAGE_SIZE} 2 ${SHARED_CPUS} ${HEARTBEAT_ENABLED}

    FLAVOR="large.float"
    flavor_create ${FLAVOR} auto 2048 ${IMAGE_SIZE} 3 ${SHARED_CPUS}
    flavor_create ${FLAVOR}${HB_FLAVOR_SUFFIX} auto 2048 ${IMAGE_SIZE} 3 ${SHARED_CPUS} ${HEARTBEAT_ENABLED}

    FLAVOR="xlarge.float"
    flavor_create ${FLAVOR} auto 4096 ${IMAGE_SIZE} 3 ${SHARED_CPUS}
    flavor_create ${FLAVOR}${HB_FLAVOR_SUFFIX} auto 4096 ${IMAGE_SIZE} 3 ${SHARED_CPUS} ${HEARTBEAT_ENABLED}

    for NODE in $(seq 0 $((NUMA_NODE_COUNT-1))); do
        ## Create custom flavors (pinned on numa node)
        if [ ${NODE} -eq 0 ]; then
            DPDK_FLAVOR_ARGS="${DEDICATED_CPUS} ${SHARED_VCPU} ${DPDK_CPU}"
        else
            # A VM cannot span Numa nodes so disable the shared vcpu
            DPDK_FLAVOR_ARGS="${DEDICATED_CPUS} ${DPDK_CPU}"
        fi
        PROCESSOR_ARGS="hw:numa_nodes=1 hw:numa_node.0=${NODE}"

        flavor_create "small.node${NODE}" auto 512 ${IMAGE_SIZE} 1 ${DEDICATED_CPUS} ${PROCESSOR_ARGS}
        flavor_create "medium.node${NODE}" auto 1024 ${IMAGE_SIZE} 2 ${DEDICATED_CPUS} ${PROCESSOR_ARGS}
        flavor_create "large.node${NODE}" auto 2048 ${IMAGE_SIZE} 3 ${DEDICATED_CPUS} ${PROCESSOR_ARGS}
        flavor_create "xlarge.node${NODE}" auto 4096 ${IMAGE_SIZE} 3 ${DEDICATED_CPUS} ${PROCESSOR_ARGS}
        flavor_create "medium.dpdk.node${NODE}" auto 1024 ${IMAGE_SIZE} 2 ${DPDK_FLAVOR_ARGS} ${PROCESSOR_ARGS}
        flavor_create "large.dpdk.node${NODE}" auto 2048 ${IMAGE_SIZE} 3 ${DPDK_FLAVOR_ARGS} ${PROCESSOR_ARGS}
        flavor_create "xlarge.dpdk.node${NODE}" auto 4096 ${IMAGE_SIZE} 3 ${DPDK_FLAVOR_ARGS} ${PROCESSOR_ARGS}
    done

    return 0
}


function setup_minimal_flavors()
{
    local DPDK_FLAVOR_ARGS="${DEDICATED_CPUS} ${SHARED_VCPU} ${DPDK_CPU}"

    flavor_create "small" auto 512 ${IMAGE_SIZE} 1 ${DEDICATED_CPUS}
    flavor_create "medium.dpdk" auto 1024 ${IMAGE_SIZE} 2 ${DPDK_FLAVOR_ARGS}
    flavor_create "small.float" auto 512 ${IMAGE_SIZE} 1 ${SHARED_CPUS}

    return 0
}

function create_custom_flavors()
{
    local FLAVORLIST=(${FLAVORS})
    local CUSTOM_NAME=""
    local CUSTOM_ID="auto"
    local CUSTOM_CORES=0
    local CUSTOM_MEM=0
    local CUSTOM_DISK=0
    local CUSTOM_DEDICATED=""
    local CUSTOM_HEARTBEAT=""
    local CUSTOM_NUMA0=""
    local CUSTOM_NUMA1=""
    local CUSTOM_NUMA_NODES=""
    local CUSTOM_VCPUMODEL=""
    local CUSTOM_SHARED_CPUS=""
    local CUSTOM_NOVA_STORAGE=""

    if is_stage_complete "custom_flavors"; then
        info "Skipping custom flavors; already done"
        return 0
    fi

    info "Adding custom flavors"

    for INDEX in ${!FLAVORLIST[@]}; do
        ENTRY=${FLAVORLIST[${INDEX}]}
        DATA=(${ENTRY//|/ })
        CUSTOM_NAME=${DATA[0]}
        log "  Adding flavor ${ENTRY}"

        ## Remove the flavor name from the array
        unset DATA[0]
        DATA=(${DATA[@]})

        FLAVOR_NAME=""
        CUSTOM_CORES=1
        CUSTOM_ID="auto"
        CUSTOM_MEM=1024
        CUSTOM_DISK=${IMAGE_SIZE}
        CUSTOM_DEDICATED=""
        CUSTOM_HEARTBEAT=""
        CUSTOM_NUMA0=""
        CUSTOM_NUMA1=""
        CUSTOM_NUMA_NODES=""
        CUSTOM_VCPUMODEL=""
        CUSTOM_SHARED_CPUS=""
        CUSTOM_NOVA_STORAGE=""

        for KEYVALUE in ${DATA[@]}; do
            KEYVAL=(${KEYVALUE//=/ })
            if [ "x${KEYVAL[0]}" == "xdisk" ]; then
                CUSTOM_DISK=${KEYVAL[1]}
            elif [ "x${KEYVAL[0]}" == "xcores" ]; then
                CUSTOM_CORES=${KEYVAL[1]}
            elif [ "x${KEYVAL[0]}" == "xmem" ]; then
                CUSTOM_MEM=${KEYVAL[1]}
            elif [ "x${KEYVAL[0]}" == "xdedicated" ]; then
                CUSTOM_DEDICATED="hw:cpu_policy=dedicated"
            elif [ "x${KEYVAL[0]}" == "xheartbeat" ]; then
                CUSTOM_HEARTBEAT="sw:wrs:guest:heartbeat=True"
            elif [ "x${KEYVAL[0]}" == "xnuma_node.0" ]; then
                CUSTOM_NUMA0="hw:numa_node.0=${KEYVAL[1]}"
            elif [ "x${KEYVAL[0]}" == "xnuma_node.1" ]; then
                CUSTOM_NUMA1="hw:numa_node.0=${KEYVAL[1]}"
            elif [ "x${KEYVAL[0]}" == "xnuma_nodes" ]; then
                CUSTOM_NUMA_NODES="hw:numa_nodes=${KEYVAL[1]}"
            elif [ "x${KEYVAL[0]}" == "xvcpumodel" ]; then
                CUSTOM_VCPUMODEL="hw:cpu_model=${KEYVAL[1]}"
            elif [ "x${KEYVAL[0]}" == "xsharedcpus" ]; then
                CUSTOM_SHARED_CPUS="hw:cpu_policy=shared"
            elif [ "x${KEYVAL[0]}" == "xstorage" ]; then
                CUSTOM_NOVA_STORAGE="aggregate_instance_extra_specs:storage=${KEYVAL[1]}"
            fi
        done

        flavor_create ${CUSTOM_NAME} ${CUSTOM_ID} ${CUSTOM_MEM} ${CUSTOM_DISK} ${CUSTOM_CORES} ${CUSTOM_HEARTBEAT} ${CUSTOM_DEDICATED} ${CUSTOM_VCPUMODEL} ${CUSTOM_SHARED_CPUS} ${CUSTOM_NUMA0} ${CUSTOM_NUMA1} ${CUSTOM_NUMA_NODES} ${CUSTOM_NOVA_STORAGE}
    done

    stage_complete "custom_flavors"

    return 0
}

# Setup flavors only used by AVS benchmarking
#
function setup_avs_flavors()
{
    local DPDK_FLAVOR_ARGS="${DEDICATED_CPUS} ${SHARED_VCPU} ${DPDK_CPU}"
    local CPU_REALTIME_ARGS="${CPU_REALTIME} ${CPU_REALTIME_MASK}"

    flavor_create "small" auto 512 ${IMAGE_SIZE} 1 ${DEDICATED_CPUS}
    flavor_create "medium" auto 1024 ${IMAGE_SIZE} 2 ${DEDICATED_CPUS}
    flavor_create "medium.dpdk" auto 1024 ${IMAGE_SIZE} 2 ${DPDK_FLAVOR_ARGS} ${CPU_REALTIME_ARGS}
    flavor_create "large.dpdk" auto 2048 ${IMAGE_SIZE} 3 ${DPDK_FLAVOR_ARGS} ${CPU_REALTIME_ARGS}

    for NODE in 0 1; do
        ## Create custom flavors (pinned on numa node)
        if [ ${NODE} -eq 0 ]; then
            DPDK_FLAVOR_ARGS="${DEDICATED_CPUS} ${SHARED_VCPU} ${DPDK_CPU}"
        else
            # A VM cannot span Numa nodes so disable the shared vcpu
            DPDK_FLAVOR_ARGS="${DEDICATED_CPUS} ${DPDK_CPU}"
        fi
        PROCESSOR_ARGS="hw:numa_nodes=1 hw:numa_node.0=${NODE}"

        flavor_create "small.node${NODE}" auto 512 ${IMAGE_SIZE} 1 ${DEDICATED_CPUS} ${PROCESSOR_ARGS}
        flavor_create "medium.node${NODE}" auto 1024 ${IMAGE_SIZE} 2 ${DEDICATED_CPUS} ${PROCESSOR_ARGS}
        flavor_create "medium.dpdk.node${NODE}" auto 1024 ${IMAGE_SIZE} 2 ${DPDK_FLAVOR_ARGS} ${PROCESSOR_ARGS} ${CPU_REALTIME_ARGS}
        flavor_create "large.dpdk.node${NODE}" auto 2048 ${IMAGE_SIZE} 3 ${DPDK_FLAVOR_ARGS} ${PROCESSOR_ARGS} ${CPU_REALTIME_ARGS}
    done

    return 0
}

## Setup flavors
##
function setup_flavors()
{
    if is_stage_complete "flavors"; then
        info "Skipping flavor configuration; already done"
        return 0
    fi

    info "Adding ${FLAVOR_TYPES} VM flavors"

    if [ "x${FLAVOR_TYPES}" == "xall" ]; then
        setup_all_flavors
        RET=$?
    elif [ "x${FLAVOR_TYPES}" == "xavs" ]; then
        setup_avs_flavors
    else
        setup_minimal_flavors
        RET=$?
    fi

    stage_complete "flavors"

    return ${RET}
}

## Setup keys
##
function setup_keys()
{
    local PRIVKEY="${HOME}/.ssh/id_rsa"
    local PUBKEY="${PRIVKEY}.pub"
    local KEYNAME=""
    local TENANT=""
    local ID=""

    if is_stage_complete "public_keys"; then
        info "Skipping public key configuration; already done"
        return 0
    fi

    info "Adding VM public keys"

    if [ -f ${HOME}/id_rsa.pub ]; then
        ## Use a user defined public key instead of the local user public key
        ## if one is found in the home directory
        PUBKEY="${HOME}/id_rsa.pub"
    elif [ ! -f ${PRIVKEY} ]; then
        log "Generating new SSH key pair for ${USER}"
        ssh-keygen -q -N "" -f ${PRIVKEY}
        RET=$?
        if [ ${RET} -ne 0 ]; then
	        echo "Failed to generate SSH key pair"
            return ${RET}
        fi
    fi

    for TENANT in ${TENANTS[@]}; do
        source ${HOME}/openrc.${TENANT}
        KEYNAME="keypair-${TENANT}"
        ID=`nova ${REGION_OPTION} keypair-list | grep -E ${KEYNAME}[^0-9] | awk '{print $2}'`
        if [ -z "${ID}" ]; then
            log_command "nova ${REGION_OPTION} keypair-add --pub-key ${PUBKEY} ${KEYNAME}"
        fi
    done

    stage_complete "public_keys"

    return 0
}

## Setup floating IP addresses for each tenant
##
function setup_floating_ips()
{
    local TENANT=""
    local COUNT=0

    if [ "${FLOATING_IP}" != "yes" ]; then
        return 0
    fi

    if is_stage_complete "floating_ips"; then
        info "Skipping floating IP address configuration; already done"
        return 0
    fi

    info "Adding floating IP addresses"

    for TENANT in ${TENANTS[@]}; do
        source ${HOME}/openrc.${TENANT}
        COUNT=$(openstack ${REGION_OPTION} floating ip list | grep -E "[a-zA-Z0-9]{8}-" | wc -l)
        if [ ${COUNT} -ge ${APPCOUNT} ]; then
            continue
        fi
        for I in $(seq 1 $((APPCOUNT - ${COUNT}))); do
            log_command "openstack ${REGION_OPTION} floating ip create ${EXTERNALNET}"
        done
    done

    stage_complete "floating_ips"

    return 0
}

## Create networks for Ixia
##
function setup_ixia_networks()
{
    local TRANSPARENT_ARGS=""
    local TENANTNUM=0
    local DHCPARGS="--no-dhcp"
    local POOLARGS=""

    if is_stage_complete "ixia_networks"; then
        info "Skipping tenant networks configuration; already done"
        return 0
    fi

    if [ "${ROUTED_TENANT_NETWORKS}" == "no" ]; then
        ## Not required.
        return 0
    fi

    if [ "${SHARED_TENANT_NETWORKS}" == "no" ]; then
        ## Not compatible
        echo "SHARED_TENANT_NETWORKS must be set to \"yes\" for ROUTED_TENANT_NETWORKS"
        return 1
    fi

    info "Adding Ixia networks"

    for TENANT in ${TENANTS[@]}; do
        source ${HOME}/openrc.${TENANT}
        local IXIANET="${TENANT}-ixia-net0"
        local IXIASUBNET="${TENANT}-ixia-subnet0"
        local IXIAROUTER="${TENANT}-ixia0"
        local SUBNET=172.$((16 + ${TENANTNUM} * 2)).0
        local SUBNETCIDR=${SUBNET}.0/24
        local IXIAGWY=${SUBNET}.31

        if [ "${VLAN_TRANSPARENT}" == "True" ]; then
            TRANSPARENT_ARGS="--transparent-vlan"
        fi

        ID=$(get_network_id ${IXIANET})
        if [ -z "${ID}" ]; then
            log_command "openstack ${REGION_OPTION} network create ${IXIANET}"
        fi

        ID=$(get_subnet_id ${IXIASUBNET})
        if [ -z "${ID}" ]; then
            log_command "openstack ${REGION_OPTION} subnet create ${IXIASUBNET} ${DHCPARGS} ${POOLARGS} --network ${IXIANET} --subnet-range ${SUBNETCIDR}"
        fi

        ID=$(get_router_id ${IXIAROUTER})
        if [ -z "${ID}" ]; then
            log_command "openstack ${REGION_OPTION} router create ${IXIAROUTER}"
            log_command "openstack ${REGION_OPTION} router add subnet ${IXIAROUTER} ${IXIASUBNET}"
        fi

        TENANTNUM=$((TENANTNUM + 1))
    done

    stage_complete "ixia_networks"

    return 0
}

## Create networks for tenants
##
function setup_tenant_networks()
{
    local TRANSPARENT_ARGS=""
    local OWNERSHIP=""
    local PROVIDERARGS=""
    local SHAREDARGS=""
    local DHCPARGS=""
    local PORT_SECURITY_ARGS=""
    local TENANT=""
    local LIMIT=0
    local ID=0
    local TENANTNUM=0

    if is_stage_complete "tenant_networks"; then
        info "Skipping tenant networks configuration; already done"
        return 0
    fi

    info "Adding tenant networks"

    if [ "${EXTRA_NICS}" != "yes" ]; then
       stage_complete "tenant_networks"
       return 0
    fi

    if [ "x${TENANTNET_DHCP}" != "xyes" ]; then
        DHCPARGS="--no-dhcp"
    fi

    if [ "${NEUTRON_PORT_SECURITY}" == "True" ]; then
	PORT_SECURITY_ARGS="--enable-port-security"
    fi

    if [ "${NEUTRON_PORT_SECURITY}" == "False" ]; then
	PORT_SECURITY_ARGS="--disable-port-security"
    fi

    for TENANT in ${TENANTS[@]}; do
        source ${HOME}/openrc.${TENANT}
        local TENANTNET="${TENANT}-net"
        local TENANTSUBNET="${TENANT}-subnet"

        if [ "x${SHARED_TENANT_NETWORKS}" == "xyes" ]; then
            source ${HOME}/openrc.admin
            OWNERSHIP="--project ${TENANT}"
            SHAREDARGS="--share"
        fi

        LIMIT=$((NETCOUNT - 1))
        if [ "x${REUSE_NETWORKS}" == "xyes" ]; then
            ## Create only a single network
            LIMIT=0
        fi

        for I in $(seq 0 ${LIMIT}); do
            GATEWAYARGS="--gateway none"
            if [ "${ROUTED_TENANT_NETWORKS}" == "yes" ]; then
                SUBNET=172.31.${I}
                SUBNETCIDR=${SUBNET}.0/24
                PEERGWY=${SUBNET}.$((1 + (1 - ${TENANTNUM})))
                GATEWAYARGS="--gateway ${SUBNET}.$((1 + ${TENANTNUM}))"
            else
                SUBNET=172.$((16 + ${TENANTNUM} * 2)).${I}
                SUBNETCIDR=${SUBNET}.0/24
            fi

            # The nova boot commands are setup to statically assign
            # addresses to each VM instance so we need to make sure that
            # any dynamic addresses (i.e., DHCP port addresses) are not in
            # conflict with any addresses that are chosen by this script.
            POOLARGS="--allocation-pool start=${SUBNET}.128,end=${SUBNET}.254"

            TENANTNETID=$(get_network_id ${TENANTNET}${I})
            if [ -z "${TENANTNETID}" ]; then
                log_command "openstack ${REGION_OPTION} network create ${OWNERSHIP} ${SHAREDARGS} ${TENANTNET}${I} ${PORT_SECURITY_ARGS}"
                TENANTNETID=$(get_network_id ${TENANTNET}${I})
            fi

            ID=$(get_subnet_id ${TENANTSUBNET}${I})
            if [ -z "${ID}" ]; then
                log_command "openstack ${REGION_OPTION} subnet create ${OWNERSHIP} ${TENANTSUBNET}${I} ${DHCPARGS} ${POOLARGS} ${GATEWAYARGS} --network ${TENANTNET}${I} --subnet-range ${SUBNETCIDR}"

                if [ "${ROUTED_TENANT_NETWORKS}" == "yes" ]; then
                    log_command "openstack ${REGION_OPTION} router add subnet ${TENANT}-ixia0 ${TENANTSUBNET}${I}"
                    for J in $(seq 1 ${IXIA_PORT_PAIRS}); do
                        ROUTES=""
                        PORT_OFFSET=$(((${J} - 1)*10))
                        IXIAGWY=172.$((16 + ${TENANTNUM} * 2)).0.$((31 + ${PORT_OFFSET}))

                        BASE=$(((100 * (${TENANTNUM} + 1)) + ${PORT_OFFSET}))
                        ROUTES="${ROUTES} --route destination=10.$((BASE + ${I})).0.0/24,gateway=${IXIAGWY}"
                        BASE=$(((100 * ((1 - ${TENANTNUM}) + 1)) + ${PORT_OFFSET}))
                        ROUTES="${ROUTES} --route destination=10.$((BASE + ${I})).0.0/24,gateway=${PEERGWY}"
                        log_command "openstack ${REGION_OPTION} router set ${TENANT}-ixia0 ${ROUTES}"
                   done
                fi
            fi
        done

        TENANTNUM=$((TENANTNUM + 1))
    done

    stage_complete "tenant_networks"

    return 0
}

function setup_port()
{
    TENANT=$1
    NETWORKID=$2
    NAME=$3
    VIF_MODEL=$4

    VNIC_TYPE=${5:-"normal"}
    IPADDRESS=${6:-""}

    local IPARGS=""
    local VNICARGS=""
    local BINDINGARGS=""
    local OWNERSHIP="--project ${TENANT}"

    if [ ! -z ${IPADDRESS} ]; then
        IPARGS="--fixed-ip ip-address=${IPADDRESS}"
    fi

    if [ ! -z ${VNIC_TYPE} ]; then
        VNICARGS="--vnic-type ${VNIC_TYPE}"
    fi

    if [ ${VNIC_TYPE} == "normal" ] && [ "${VSWITCH_TYPE}" == "avs" ]; then
        BINDINGARGS="--binding-profile vif_model=${VIF_MODEL}"
    fi

    # Need to run as admin to set --binding-profile and --project
    source ${HOME}/openrc.admin

    log_command "openstack port create --network ${NETWORKID} ${OWNERSHIP} ${IPARGS} ${VNICARGS} ${BINDINGARGS} ${NAME}"
}

## Setup management ports
##
function setup_management_ports()
{
    local CREATE_PORT="no"
    local TENANTNUM=0

    if is_stage_complete "management_ports"; then
        info "Skipping management ports configuration; already done"
        return 0
    fi

    info "Adding management ports"

    if [ "${EXTRA_NICS}" != "yes" ]; then
       stage_complete "management_ports"
       return 0
    fi

    for INDEX in ${!APPTYPES[@]}; do
        VMTYPE=${VMTYPES[${INDEX}]}
        if [ "x${MGMT_VIF_MODEL}" == "x${VMTYPE}" ]; then
            CREATE_PORT=${CREATE_PORT_TYPES[${INDEX}]}
        fi
    done

    if [ "${CREATE_PORT}" != "yes" ]; then
       stage_complete "management_ports"
       return 0
    fi

    for TENANT in ${TENANTS[@]}; do
        source ${HOME}/openrc.${TENANT}
        MGMTCOUNTER=0

        for INDEX in ${!APPTYPES[@]}; do
            APPTYPE=${APPTYPES[${INDEX}]}
            VMTYPE=${VMTYPES[${INDEX}]}
            APP_VARNAME=${APPTYPE}APPS
            APPS=(${!APP_VARNAME})
            VMCOUNTER=1
            for I in ${!APPS[@]}; do
                ENTRY=${APPS[${I}]}
                DATA=(${ENTRY//|/ })
                NUMVMS=${DATA[0]}

                for J in $(seq 1 ${NUMVMS}); do
                    if [ ${APPCOUNT} -ge ${MGMTNETS} ]; then
                        ## Spread the VM instances evenly over the number of mgmt networks.
                        MGMTNETNUMBER=$((MGMTCOUNTER / (${APPCOUNT} / ${MGMTNETS})))
                    else
                        MGMTNETNUMBER=0
                    fi

                    MGMTNET=$(get_mgmt_network_name ${TENANT}-mgmt-net ${MGMTNETNUMBER})
                    MGMTNETID=$(get_network_id ${MGMTNET})
                    if [ -z "${MGMTNETID}" ]; then
                        echo "Unable to find management network: ${MGMTNET}"
                        return 1
                    fi
                    MGMTPORTNAME=port-${MGMTNET}-${VMTYPE}${VMCOUNTER}

                    setup_port "${TENANT}" "${MGMTNET}" "${MGMTPORTNAME}" "${MGMT_VIF_MODEL}"

                    MGMTCOUNTER=$((MGMTCOUNTER+1))
                    VMCOUNTER=$((VMCOUNTER+1))
                done
            done
        done
        TENANTNUM=$((TENANTNUM + 1))
    done

    stage_complete "management_ports"

    return 0
}

## Setup tenant ports
##
function setup_tenant_ports()
{
    local CREATE_PORT="no"
    local TENANTNUM=0
    local OWNER=""

    if is_stage_complete "tenant_ports"; then
        info "Skipping tenant ports configuration; already done"
        return 0
    fi

    info "Adding tenant ports"

    if [ "${EXTRA_NICS}" != "yes" ]; then
       stage_complete "tenant_ports"
       return 0
    fi

    for TENANT in ${TENANTS[@]}; do
        TENANTNET="${TENANT}-net"
        NETCOUNTER=0

        if [ "x${SHARED_TENANT_NETWORKS}" == "xyes" ] && [ ${TENANTNUM} -gt 0 ]; then
            source ${HOME}/openrc.admin
            OWNER="${TENANTS[$((1 - ${TENANTNUM}))]}"
        else
            source ${HOME}/openrc.${TENANT}
            OWNER="${TENANT}"
        fi

        for INDEX in ${!APPTYPES[@]}; do
            CREATE_PORT=${CREATE_PORT_TYPES[${INDEX}]}
            if [ "x${CREATE_PORT}" == "xno" ]; then
                continue
            fi

            NIC1_VIF_MODEL=${NIC1_VIF_MODELS[${INDEX}]}
            if [ -z ${NIC1_VIF_MODEL} ]; then
                continue
            fi

            NIC1_VNIC_TYPE=${NIC1_VNIC_TYPES[${INDEX}]}
            VMTYPE=${VMTYPES[${INDEX}]}
            APPTYPE=${APPTYPES[${INDEX}]}
            APP_VARNAME=${APPTYPE}APPS
            APPS=(${!APP_VARNAME})
            VMCOUNTER=1
            for I in ${!APPS[@]}; do
                ENTRY=${APPS[${I}]}
                DATA=(${ENTRY//|/ })
                NUMVMS=${DATA[0]}

                for J in $(seq 1 ${NUMVMS}); do
                    ## Determine actual network number and host number for this VM
                    NETNUMBER=$((NETCOUNTER / ${VMS_PER_NETWORK}))
                    if [ "x${REUSE_NETWORKS}" == "xyes" ]; then
                        ## Use only a single network
                        NETNUMBER=0
                    fi
                    HOSTNUMBER=$((NETCOUNTER % ${VMS_PER_NETWORK}))

                    TENANTNETID=$(get_network_id ${TENANTNET}${NETNUMBER})
                    if [ "x${ROUTED_TENANT_NETWORKS}" == "xyes" ]; then
                        ## Not needed, as the VM will just be bridging.
                        TENANTIPADDR=""
                    else
                        TENANTIPADDR=$(get_network_ip_address ${NETNUMBER} ${NETCOUNTER} ${TENANTNUM})
                    fi
                    TENANTPORTNAME=port-${TENANTNET}${NETNUMBER}-${VMTYPE}${VMCOUNTER}

                    setup_port "${OWNER}" "${TENANTNET}${NETNUMBER}" "${TENANTPORTNAME}" "${NIC1_VIF_MODEL}" "${NIC1_VNIC_TYPE}" "${TENANTIPADDR}"

                    NETCOUNTER=$((NETCOUNTER+1))
                    VMCOUNTER=$((VMCOUNTER+1))
                done
            done
        done
        TENANTNUM=$((TENANTNUM + 1))
    done

    stage_complete "tenant_ports"

    return 0
}


## Setup internal ports
##
function setup_internal_ports()
{
    local CREATE_PORT="no"
    local TENANTNUM=0
    local VLANID=0

    if is_stage_complete "internal_ports"; then
        info "Skipping internal ports configuration; already done"
        return 0
    fi

    info "Adding internal ports"

    if [ "${SHARED_TENANT_NETWORKS}" == "yes" -o "${EXTRA_NICS}" != "yes" ]; then
        ## Internal networks are not required since VM instances will be
        ## directly connected to tenant data networks see comment describing
        ## the use of this variable.
        stage_complete "internal_ports"
        return 0
    fi

    for TENANT in ${TENANTS[@]}; do
        source ${HOME}/openrc.${TENANT}
        NETCOUNTER=0
        for INDEX in ${!APPTYPES[@]}; do
            CREATE_PORT=${CREATE_PORT_TYPES[${INDEX}]}
            if [ "x${CREATE_PORT}" == "xno" ]; then
                continue
            fi

            NIC2_VIF_MODEL=${NIC2_VIF_MODELS[${INDEX}]}
            NIC2_VNIC_TYPE=${NIC2_VNIC_TYPES[${INDEX}]}
            VMTYPE=${VMTYPES[${INDEX}]}
            APPTYPE=${APPTYPES[${INDEX}]}
            APP_VARNAME=${APPTYPE}APPS
            APPS=(${!APP_VARNAME})
            VMCOUNTER=1
            for I in ${!APPS[@]}; do
                ENTRY=${APPS[${I}]}
                DATA=(${ENTRY//|/ })
                NUMVMS=${DATA[0]}

                for J in $(seq 1 ${NUMVMS}); do
                    ## Determine actual network number and host number for this VM
                    NETNUMBER=$((NETCOUNTER / ${VMS_PER_NETWORK}))
                    HOSTNUMBER=$((NETCOUNTER % ${VMS_PER_NETWORK}))
                    NET=$((${NETNUMBER} / ${MAXVLANS}))

                    if [ "x${REUSE_NETWORKS}" != "xyes" -a "x${ROUTED_TENANT_NETWORKS}" != "xyes" ]; then
                        VLANID=$(((NETNUMBER % ${MAXVLANS}) + ${FIRSTVLANID}))
                    fi


                    INTERNALNETNAME=${INTERNALNET}${NET}
                    INTERNALNETID=$(get_network_id ${INTERNALNETNAME})
                    INTERNALPORTNAME=port-${TENANT}-${INTERNALNETNAME}-${VMTYPE}${VMCOUNTER}

                    setup_port "${TENANT}" "${INTERNALNETNAME}" "${INTERNALPORTNAME}" "${NIC2_VIF_MODEL}" "${NIC2_VNIC_TYPE}"


                    if [ ${VLANID} -ne 0 ]; then
                        INTERNALNETNAME=${INTERNALNET}${NET}-${VLANID}
                        INTERNALNETID=$(get_network_id ${INTERNALNETNAME})
                        INTERNALPORTNAME=port-${TENANT}-${INTERNALNETNAME}-${VMTYPE}${VMCOUNTER}
                        setup_port "${TENANT}" "${INTERNALNETNAME}" "${INTERNALPORTNAME}" "${NIC2_VIF_MODEL}" "${NIC2_VNIC_TYPE}"
                    fi

                    NETCOUNTER=$((NETCOUNTER+1))
                    VMCOUNTER=$((VMCOUNTER+1))
                done
            done
        done
        TENANTNUM=$((TENANTNUM + 1))
    done

    stage_complete "internal_ports"
    return 0
}

## Create a per-VM userdata file to setup the layer2 bridge test.  The VM
## will be setup to bridge traffic between its 2nd and 3rd NIC
##
function create_layer2_userdata()
{
    local VMNAME=$1
    local VMTYPE=$2
    local NETTYPE=$3
    local TENANTNUM=$4
    local NETNUMBER=$5
    local HOSTNUMBER=$6
    local VLANID=$7
    local TENANTMTU=$8
    local INTERNALMTU=$9

    local USERDATA=${USERDATA_DIR}/${VMNAME}_userdata.txt

    BRIDGE_MTU=$(($TENANTMTU < $INTERNALMTU ? $TENANTMTU : $INTERNALMTU))

    if [ "${NETTYPE}" == "kernel" ]; then
        cat << EOF > ${USERDATA}
#wrs-config

FUNCTIONS="bridge,${EXTRA_FUNCTIONS}"
LOW_LATENCY="${LOW_LATENCY}"
BRIDGE_PORTS="${DEFAULT_IF1},${DEFAULT_IF2}.${VLANID}"
BRIDGE_MTU="${BRIDGE_MTU}"
EOF
        sed -i -e "s#\(BRIDGE_PORTS\)=.*#\1=\"${DEFAULT_IF1},${DEFAULT_IF2}.${VLANID}\"#g" ${USERDATA}
        sed -i -e "s#\(FUNCTIONS\)=.*#\1=\"bridge\"#g" ${USERDATA}
    else
	NIC_DEVICE=$(get_guest_nic_device $VMTYPE)

        cat << EOF > ${USERDATA}
#wrs-config

FUNCTIONS="hugepages,vswitch,${EXTRA_FUNCTIONS}"
LOW_LATENCY="${LOW_LATENCY}"
BRIDGE_PORTS="${DEFAULT_IF0},${DEFAULT_IF1}.${VLANID}"
BRIDGE_MTU="${BRIDGE_MTU}"
NIC_DEVICE="${NIC_DEVICE}"
EOF
        if [ ! -z "${VSWITCH_ENGINE_IDLE_DELAY+x}" ]; then
            echo "VSWITCH_ENGINE_IDLE_DELAY=${VSWITCH_ENGINE_IDLE_DELAY}" >> ${USERDATA}
        fi
        if [ ! -z "${VSWITCH_MEM_SIZES+x}" ]; then
            echo "VSWITCH_MEM_SIZES=${VSWITCH_MEM_SIZES}" >> ${USERDATA}
        fi
        if [ ! -z "${VSWITCH_MBUF_POOL_SIZE+x}" ]; then
            echo "VSWITCH_MBUF_POOL_SIZE=${VSWITCH_MBUF_POOL_SIZE}" >> ${USERDATA}
        fi
        if [ ! -z "${VSWITCH_ENGINE_PRIORITY+x}" ]; then
            echo "VSWITCH_ENGINE_PRIORITY=${VSWITCH_ENGINE_PRIORITY}" >> ${USERDATA}
        fi
    fi

    echo ${USERDATA}
    return 0
}

## Create a per-VM userdata file to setup the layer3 routing test.  The VM
## will be setup to route traffic between its 2nd and 3rd NIC according to the
## IP addresses and routes supplied in the ADDRESSES and ROUTES variables.
##
##
function create_layer3_userdata()
{
    local VMNAME=$1
    local VMTYPE=$2
    local NETTYPE=$3
    local TENANTNUM=$4
    local NETNUMBER=$5
    local HOSTNUMBER=$6
    local VLANID=$7
    local TENANTMTU=$8
    local INTERNALMTU=$9
    local IFNAME1="${DEFAULT_IF1}"
    local IFNAME2="${DEFAULT_IF2}"

    local USERDATA=${USERDATA_DIR}/${VMNAME}_userdata.txt

    if [ "${NETTYPE}" == "kernel" ]; then
        local FUNCTIONS="routing,${EXTRA_FUNCTIONS}"
    elif [ "${NETTYPE}" == "vswitch" ]; then
        local FUNCTIONS="hugepages,avr,${EXTRA_FUNCTIONS}"
        IFNAME1="${DEFAULT_IF0}"
        IFNAME2="${DEFAULT_IF1}"
    else
        echo "layer3 user data for type=${NETTYPE} is not supported"
        exit 1
    fi

    NIC_DEVICE=$(get_guest_nic_device $VMTYPE)

    if [ "0${VLANID}" -ne 0 ]; then
        IFNAME2="${IFNAME2}.${VLANID}"
    fi

    ## Setup static routes between IXIA -> VM0 -> VM1 -> IXIA for 4 Ixia static
    ## subnets and 4 connected interface subnets.
    ##
    ## Static traffic will look like the following where the leading prefix (10)
    ## will increment by 10 based on the HOSTNUMBER variable to allow different
    ## ranges for each VM instance on the network:
    ##    10.160.*.* -> 10.180.*.*
    ##    10.170.*.* -> 10.190.*.*
    ##
    ## Connected interface traffic will look like this:
    ##    172.16.*.* -> 172.18.*.*
    ##    172.19.*.* -> 172.17.*.*
    ##
    ## The gateway addresses will look like this:
    ##    172.16.*.{2,4,6...} -> 172.16.*.{1,3,5...} -> 10.1.*.{1,3,5...} -> +
    ##                                                                       |
    ##    172.18.*.{2,4,6...} <- 172.18.*.{1,3,5...} <- 10.1.*.{2,4,6...} <- +
    ##
    ##
    ##
    PREFIX=$((10 * (1 + ${HOSTNUMBER})))
    MY_HOSTBYTE=$((1 + (${HOSTNUMBER} * 2)))
    IXIA_HOSTBYTE=$((2 + (${HOSTNUMBER} * 2)))

    if [ "${SHARED_TENANT_NETWORKS}" == "yes" ]; then
        # directly connected to both networks, therefore setup local addresses
        # only and no routes for the internal network.
        cat << EOF > ${USERDATA}
#wrs-config

FUNCTIONS=${FUNCTIONS}
LOW_LATENCY="${LOW_LATENCY}"
NIC_DEVICE=${NIC_DEVICE}
ADDRESSES=(
    "172.16.${NETNUMBER}.${MY_HOSTBYTE},255.255.255.0,${IFNAME1},${TENANTMTU}"
    "172.18.${NETNUMBER}.${MY_HOSTBYTE},255.255.255.0,${IFNAME2},${TENANTMTU}"
    )
ROUTES=()
EOF
    elif [ ${TENANTNUM} -eq 0 ]; then
        MY_P2PBYTE=$((1 + (${HOSTNUMBER} * 2)))
        PEER_P2PBYTE=$((2 + (${HOSTNUMBER} * 2)))

        cat << EOF > ${USERDATA}
#wrs-config

FUNCTIONS=${FUNCTIONS}
LOW_LATENCY="${LOW_LATENCY}"
NIC_DEVICE=${NIC_DEVICE}
ADDRESSES=(
    "172.16.${NETNUMBER}.${MY_HOSTBYTE},255.255.255.0,${IFNAME1},${TENANTMTU}"
    "10.1.${NETNUMBER}.${MY_P2PBYTE},255.255.255.0,${IFNAME2},${INTERNALMTU}"
    )
ROUTES=(
    "${PREFIX}.160.${NETNUMBER}.0/24,172.16.${NETNUMBER}.${IXIA_HOSTBYTE},${IFNAME1}"
    "${PREFIX}.170.${NETNUMBER}.0/24,172.16.${NETNUMBER}.${IXIA_HOSTBYTE},${IFNAME1}"
    "${PREFIX}.180.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
    "${PREFIX}.190.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
    "172.18.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
    "172.19.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
    )
EOF

    else
        MY_P2PBYTE=$((2 + (${HOSTNUMBER} * 2)))
        PEER_P2PBYTE=$((1 + (${HOSTNUMBER} * 2)))

        cat << EOF > ${USERDATA}
#wrs-config

FUNCTIONS=${FUNCTIONS}
LOW_LATENCY="${LOW_LATENCY}"
NIC_DEVICE=${NIC_DEVICE}
ADDRESSES=(
    "172.18.${NETNUMBER}.${MY_HOSTBYTE},255.255.255.0,${IFNAME1},${TENANTMTU}"
    "10.1.${NETNUMBER}.${MY_P2PBYTE},255.255.255.0,${IFNAME2},${INTERNALMTU}"
    )
ROUTES=(
    "${PREFIX}.180.${NETNUMBER}.0/24,172.18.${NETNUMBER}.${IXIA_HOSTBYTE},${IFNAME1}"
    "${PREFIX}.190.${NETNUMBER}.0/24,172.18.${NETNUMBER}.${IXIA_HOSTBYTE},${IFNAME1}"
    "${PREFIX}.160.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
    "${PREFIX}.170.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
    "172.16.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
    "172.17.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
    )
EOF

    fi

    if [ ! -z "${VSWITCH_ENGINE_IDLE_DELAY+x}" ]; then
        echo "VSWITCH_ENGINE_IDLE_DELAY=${VSWITCH_ENGINE_IDLE_DELAY}" >> ${USERDATA}
    fi
    if [ ! -z "${VSWITCH_MEM_SIZES+x}" ]; then
        echo "VSWITCH_MEM_SIZES=${VSWITCH_MEM_SIZES}" >> ${USERDATA}
    fi
    if [ ! -z "${VSWITCH_MBUF_POOL_SIZE+x}" ]; then
        echo "VSWITCH_MBUF_POOL_SIZE=${VSWITCH_MBUF_POOL_SIZE}" >> ${USERDATA}
    fi
    if [ ! -z "${VSWITCH_ENGINE_PRIORITY+x}" ]; then
        echo "VSWITCH_ENGINE_PRIORITY=${VSWITCH_ENGINE_PRIORITY}" >> ${USERDATA}
    fi

    echo ${USERDATA}
    return 0
}


## Create a per-VM userdata file to setup the layer2 bridge test.  The VM
## will be setup to bridge traffic between its 2nd and 3rd NIC
##
function create_layer2_centos_userdata()
{
    local VMNAME=$1
    local NETTYPE=$2
    local TENANTNUM=$3
    local NETNUMBER=$4
    local HOSTNUMBER=$5
    local VLANID=$6
    local TENANTMTU=$7
    local INTERNALMTU=$8

    local USERDATA=${USERDATA_DIR}/${VMNAME}_userdata.txt

    # Initially, just worry about enabling login
    # TODO:  Add networking at a later data

    cat << EOF > ${USERDATA}
#cloud-config
chpasswd:
 list: |
   root:root
   centos:centos
 expire: False
ssh_pwauth: True
EOF

    echo ${USERDATA}
    return 0
}

## Create a per-VM userdata file to setup the layer3 routing test.  The VM
## will be setup to route traffic between its 2nd and 3rd NIC according to the
## IP addresses and routes supplied in the ADDRESSES and ROUTES variables.
##
##
function create_layer3_centos_userdata()
{
    local VMNAME=$1
    local NETTYPE=$2
    local TENANTNUM=$3
    local NETNUMBER=$4
    local HOSTNUMBER=$5
    local VLANID=$6
    local TENANTMTU=$7
    local INTERNALMTU=$8
    local IFNAME1="${DEFAULT_IF1}"
    local IFNAME2="${DEFAULT_IF2}"

    local USERDATA=${USERDATA_DIR}/${VMNAME}_userdata.txt

    # Initially, just worry about enabling login
    # TODO:  Add networking at a later data

    cat << EOF > ${USERDATA}
#cloud-config
chpasswd:
 list: |
   root:root
   centos:centos
 expire: False
ssh_pwauth: True
EOF

    echo ${USERDATA}
    return 0
}

## Create a per-VM userdata file to setup the networking in the guest
## according to the NETWORKING_TYPE variable.
##
function create_userdata
{
    local VMNAME=$1
    local VMTYPE=$2
    local NETTYPE=$3
    local TENANTNUM=$4
    local NETNUMBER=$5
    local HOSTNUMBER=$6
    local VLANID=$7
    local TENANTMTU=$8
    local INTERNALMTU=$9
    local IMAGE=$10


    if [ "x${IMAGE}" == "xcentos" -o "x${IMAGE}" == "xcentos_raw" ]; then
        if [ "x${NETWORKING_TYPE}" == "xlayer3" ]; then
            create_layer3_centos_userdata ${VMNAME} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU}
        else
            create_layer2_centos_userdata ${VMNAME} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU}
        fi
    else
        if [ "x${NETWORKING_TYPE}" == "xlayer3" ]; then
            create_layer3_userdata ${VMNAME} ${VMTYPE} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU}
        else
            create_layer2_userdata ${VMNAME} ${VMTYPE} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU}
        fi
    fi

    return $?
}

## Create a per-VM userdata file to setup the layer2 bridge test.  The VM
## will be setup to bridge traffic between its 2nd and 3rd NIC
##
function append_layer2_heat_userdata()
{
    local VMNAME=$1
    local VMTYPE=$2
    local NETTYPE=$3
    local TENANTNUM=$4
    local NETNUMBER=$5
    local HOSTNUMBER=$6
    local VLANID=$7
    local TENANTMTU=$8
    local INTERNALMTU=$9
    local FILE=$10

    BRIDGE_MTU=$(($TENANTMTU < $INTERNALMTU ? $TENANTMTU : $INTERNALMTU))

    if [ "${NETTYPE}" == "kernel" ]; then
        cat << EOF >> ${FILE}
        user_data_format: 'RAW'
        user_data:
          Fn::Base64:
            Fn::Replace:
            - 'OS::stack_name': {Ref: 'OS::stack_name'}
            - |
              #wrs-config

              FUNCTIONS="bridge,${EXTRA_FUNCTIONS}"
              LOW_LATENCY="${LOW_LATENCY}"
              BRIDGE_PORTS="${DEFAULT_IF1},${DEFAULT_IF2}.${VLANID}"
              BRIDGE_MTU="${BRIDGE_MTU}"
EOF
        sed -i -e "s#\(BRIDGE_PORTS\)=.*#\1=\"${DEFAULT_IF1},${DEFAULT_IF2}.${VLANID}\"#g" ${FILE}
        sed -i -e "s#\(FUNCTIONS\)=.*#\1=\"bridge\"#g" ${FILE}
    else
	NIC_DEVICE=$(get_guest_nic_device $VMTYPE)

        cat << EOF >> ${FILE}
        user_data_format: 'RAW'
        user_data:
          Fn::Base64:
            Fn::Replace:
            - 'OS::stack_name': {Ref: 'OS::stack_name'}
            - |
              #wrs-config

              FUNCTIONS="hugepages,vswitch,${EXTRA_FUNCTIONS}"
              LOW_LATENCY="${LOW_LATENCY}"
              BRIDGE_PORTS="${DEFAULT_IF0},${DEFAULT_IF1}.${VLANID}"
              BRIDGE_MTU="${BRIDGE_MTU}"
              NIC_DEVICE="${NIC_DEVICE}"
EOF
        if [ ! -z "${VSWITCH_ENGINE_IDLE_DELAY+x}" ]; then
            echo "              VSWITCH_ENGINE_IDLE_DELAY=${VSWITCH_ENGINE_IDLE_DELAY}" >> ${FILE}
        fi
        if [ ! -z "${VSWITCH_MEM_SIZES+x}" ]; then
            echo "              VSWITCH_MEM_SIZES=${VSWITCH_MEM_SIZES}" >> ${FILE}
        fi
        if [ ! -z "${VSWITCH_MBUF_POOL_SIZE+x}" ]; then
            echo "              VSWITCH_MBUF_POOL_SIZE=${VSWITCH_MBUF_POOL_SIZE}" >> ${FILE}
        fi
        if [ ! -z "${VSWITCH_ENGINE_PRIORITY+x}" ]; then
            echo "              VSWITCH_ENGINE_PRIORITY=${VSWITCH_ENGINE_PRIORITY}" >> ${FILE}
        fi
    fi

    return 0
}

## Create a per-VM userdata file to setup the layer3 routing test.  The VM
## will be setup to route traffic between its 2nd and 3rd NIC according to the
## IP addresses and routes supplied in the ADDRESSES and ROUTES variables.
##
##
function append_layer3_heat_userdata()
{
    local VMNAME=$1
    local VMTYPE=$2
    local NETTYPE=$3
    local TENANTNUM=$4
    local NETNUMBER=$5
    local HOSTNUMBER=$6
    local VLANID=$7
    local TENANTMTU=$8
    local INTERNALMTU=$9
    local FILE=$10
    local IFNAME1="${DEFAULT_IF1}"
    local IFNAME2="${DEFAULT_IF2}"

    if [ "${NETTYPE}" == "kernel" ]; then
        local FUNCTIONS="routing,${EXTRA_FUNCTIONS}"
    elif [ "${NETTYPE}" == "vswitch" ]; then
        local FUNCTIONS="hugepages,avr,${EXTRA_FUNCTIONS}"
        IFNAME1="${DEFAULT_IF0}"
        IFNAME2="${DEFAULT_IF1}"
    else
        echo "layer3 user data for type=${NETTYPE} is not supported"
        exit 1
    fi

    NIC_DEVICE=$(get_guest_nic_device $VMTYPE)

    if [ "0${VLANID}" -ne 0 ]; then
        IFNAME2="${IFNAME2}.${VLANID}"
    fi

    ## Setup static routes between IXIA -> VM0 -> VM1 -> IXIA for 4 Ixia static
    ## subnets and 4 connected interface subnets.
    ##
    ## See comment above for detailed explanation
    ##
    PREFIX=$((10 * (1 + ${HOSTNUMBER})))
    MY_HOSTBYTE=$((1 + (${HOSTNUMBER} * 2)))
    IXIA_HOSTBYTE=$((2 + (${HOSTNUMBER} * 2)))

    if [ ${TENANTNUM} -eq 0 ]; then
        MY_P2PBYTE=$((1 + (${HOSTNUMBER} * 2)))
        PEER_P2PBYTE=$((2 + (${HOSTNUMBER} * 2)))

        cat << EOF >> ${FILE}
        user_data_format: 'RAW'
        user_data:
          Fn::Base64:
            Fn::Replace:
            - 'OS::stack_name': {Ref: 'OS::stack_name'}
            - |
              #wrs-config

              FUNCTIONS=${FUNCTIONS}
              LOW_LATENCY="${LOW_LATENCY}"
              NIC_DEVICE=${NIC_DEVICE}
              ADDRESSES=(
                  "172.16.${NETNUMBER}.$((1 + (${HOSTNUMBER} * 2))),255.255.255.0,${IFNAME1},${TENANTMTU}"
                  "10.1.${NETNUMBER}.$((1 + (${HOSTNUMBER} * 2))),255.255.255.0,${IFNAME2},${INTERNALMTU}"
                  )
              ROUTES=(
                  "${PREFIX}.160.${NETNUMBER}.0/24,172.16.${NETNUMBER}.${IXIA_HOSTBYTE},${IFNAME1}"
                  "${PREFIX}.170.${NETNUMBER}.0/24,172.16.${NETNUMBER}.${IXIA_HOSTBYTE},${IFNAME1}"
                  "${PREFIX}.180.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
                  "${PREFIX}.190.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
                  "172.18.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
                  "172.19.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
                  )
EOF
    else
        MY_P2PBYTE=$((2 + (${HOSTNUMBER} * 2)))
        PEER_P2PBYTE=$((1 + (${HOSTNUMBER} * 2)))

        cat << EOF >> ${FILE}
        user_data_format: 'RAW'
        user_data:
          Fn::Base64:
            Fn::Replace:
            - 'OS::stack_name': {Ref: 'OS::stack_name'}
            - |
              #wrs-config

              FUNCTIONS=${FUNCTIONS}
              LOW_LATENCY="${LOW_LATENCY}"
              NIC_DEVICE=${NIC_DEVICE}
              ADDRESSES=(
                  "172.18.${NETNUMBER}.$((1 + (${HOSTNUMBER} * 2))),255.255.255.0,${IFNAME1},${TENANTMTU}"
                  "10.1.${NETNUMBER}.$((2 + (${HOSTNUMBER} * 2))),255.255.255.0,${IFNAME2},${INTERNALMTU}"
                  )
              ROUTES=(
                  "${PREFIX}.180.${NETNUMBER}.0/24,172.18.${NETNUMBER}.${IXIA_HOSTBYTE},${IFNAME1}"
                  "${PREFIX}.190.${NETNUMBER}.0/24,172.18.${NETNUMBER}.${IXIA_HOSTBYTE},${IFNAME1}"
                  "${PREFIX}.160.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
                  "${PREFIX}.170.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
                  "172.16.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
                  "172.17.${NETNUMBER}.0/24,10.1.${NETNUMBER}.${PEER_P2PBYTE},${IFNAME2}"
                  )
EOF
    fi

    return 0
}


## Create a per-VM userdata file to setup the layer2 bridge test.  The VM
## will be setup to bridge traffic between its 2nd and 3rd NIC
##
function append_layer2_heat_centos_userdata()
{
    local VMNAME=$1
    local NETTYPE=$2
    local TENANTNUM=$3
    local NETNUMBER=$4
    local HOSTNUMBER=$5
    local VLANID=$6
    local TENANTMTU=$7
    local INTERNALMTU=$8
    local FILE=$9

    # Initially, just worry about enabling login
    # TODO:  Add networking at a later data

    cat << EOF >> ${FILE}
        user_data_format: 'RAW'
        user_data:
          Fn::Base64:
            Fn::Replace:
            - 'OS::stack_name': {Ref: 'OS::stack_name'}
            - |
              #cloud-config
              chpasswd:
               list: |
                 root:root
                 centos:centos
               expire: False
              ssh_pwauth: True
EOF

    return 0
}

## Create a per-VM userdata file to setup the layer3 routing test.  The VM
## will be setup to route traffic between its 2nd and 3rd NIC according to the
## IP addresses and routes supplied in the ADDRESSES and ROUTES variables.
##
##
function append_layer3_heat_centos_userdata()
{
    local VMNAME=$1
    local NETTYPE=$2
    local TENANTNUM=$3
    local NETNUMBER=$4
    local HOSTNUMBER=$5
    local VLANID=$6
    local TENANTMTU=$7
    local INTERNALMTU=$8
    local FILE=$9
    local IFNAME1="${DEFAULT_IF1}"
    local IFNAME2="${DEFAULT_IF2}"

    # Initially, just worry about enabling login
    # TODO:  Add networking at a later data

    cat << EOF >> ${FILE}
        user_data_format: 'RAW'
        user_data:
          Fn::Base64:
            Fn::Replace:
            - 'OS::stack_name': {Ref: 'OS::stack_name'}
            - |
              #cloud-config
              chpasswd:
               list: |
                 root:root
                 centos:centos
               expire: False
              ssh_pwauth: True
EOF

    return 0
}

## Create a per-VM userdata file to setup the networking in the guest
## according to the NETWORKING_TYPE variable.
##
function append_heat_userdata
{
    local VMNAME=$1
    local VMTYPE=$2
    local NETTYPE=$3
    local TENANTNUM=$4
    local NETNUMBER=$5
    local HOSTNUMBER=$6
    local VLANID=$7
    local TENANTMTU=$8
    local INTERNALMTU=$9
    local FILE=$10
    local IMAGE=$11

    if [ "x${IMAGE}" == "xcentos" -o "x${IMAGE}" == "xcentos_raw" ]; then
        if [ "x${NETWORKING_TYPE}" == "xlayer3" ]; then
            append_layer3_heat_centos_userdata ${VMNAME} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU} ${FILE}
        else
            append_layer2_heat_centos_userdata ${VMNAME} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU} ${FILE}
        fi
    else
        if [ "x${NETWORKING_TYPE}" == "xlayer3" ]; then
            append_layer3_heat_userdata ${VMNAME} ${VMTYPE} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU} ${FILE}
        else
            append_layer2_heat_userdata ${VMNAME} ${VMTYPE} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU} ${FILE}
        fi
    fi

    return 0
}

## Setup the image arguments for the nova boot command according to whether
## the user wants to use cinder volumes or glance images.
##
function create_image_args
{
    local VMNAME=$1
    local IMAGE=$2
    local BOOT_SOURCE=$3

    if [ "x${BOOT_SOURCE}" == "xglance" ]; then
        echo "--image=${IMAGE}"
    else
        # Added cinder id to launch file so now just use \$CINDER_ID
        echo "--block-device-mapping vda=\${CINDER_ID}:::0"
    fi
    return 0
}

## Create a file to later add boot commands
##
function create_boot_command_file
{
    local TENANT=$1
    local VMNAME=$2
    local RESULT=$3
    local FILE=${BOOTDIR}/launch_${VMNAME}.sh

    cat << EOF > ${FILE}
#!/bin/bash
#
source ${HOME}/openrc.${TENANT}
EOF
    chmod 755 ${FILE}

    eval "$RESULT=${FILE}"
    return 0
}

## Create a file to later add yaml statements
##
function create_heat_yaml_file
{
    local TENANT=$1
    local VMNAME=$2
    local RESULT=$3
    local FILE=${BOOTDIR}/heat_${VMNAME}.yaml

    cat << EOF > ${FILE}
heat_template_version: 2013-05-23

description: >
    Creates specified VMs from lab_setup.sh

parameters:

resources:

EOF
    chmod 755 ${FILE}

    eval "$RESULT=${FILE}"
    return 0
}

## Add Heat Parameters to a file
##
#function write_heat_parameter_commands()

function get_heat_network_resources_commands()
{
    local TENANT=$1
    local VMNAME=$2
    local MGMTNETID=$3
    local TENANTNETID=$4
    local INTERNALNETID=$5
    local NETWORKS=""

    VMTYPE=$(echo "${VMNAME}" | sed -e "s/${TENANT}//g")

    MGMTPORTID=$(openstack port list --network ${MGMTNETID} -c ID -c Name -f value | grep -E "${TENANT}.*${VMTYPE}" | awk '{print $1}')
    if [ ! -z ${MGMTPORTID} ]; then
        NETWORKS="${NETWORKS}
         - {port: ${MGMTPORTID} }"
    else
        NETWORKS="${NETWORKS}
         - {uuid: ${MGMTNETID} }"
    fi

    if [ "${EXTRA_NICS}" != "yes" ]; then
        echo "${NICS}"
        return 0
    fi

    TENANTPORTID=$(openstack port list --network ${TENANTNETID} -c ID -c Name -f value | grep -E "${TENANT}.*${VMTYPE}" | awk '{print $1}')
    if [ ! -z ${TENANTPORTID} ]; then
        NETWORKS="${NETWORKS}
         - {port: ${TENANTPORTID} }"
    else
        NETWORKS="${NETWORKS}
         - {uuid: ${TENANTNETID} }"
    fi

    if [ "x${SHARED_TENANT_NETWORKS}" == "xyes" ]; then
        TENANT="${TENANTS[$((1 - ${TENANTNUM}))]}"
    fi
    INTERNALPORTID=$(openstack port list --network ${INTERNALNETID} -c ID -c Name -f value | grep -m 1 -E "${TENANT}.*${VMTYPE}" | awk '{print $1}')
    if [ ! -z ${INTERNALPORTID} ]; then
        NETWORKS="${NETWORKS}
         - {port: ${INTERNALPORTID} }"
    else
        NETWORKS="${NETWORKS}
         - {uuid: ${INTERNALNETID} }"
    fi

    echo "${NETWORKS}"
    return 0
}

## Add Heat resources to a file
##
function write_heat_resource_commands()
{
    local TENANT=${1}
    local VMNAME=${2}
    local VOLNAME=${3}
    local IMAGE=${4}
    local BOOT_SOURCE=${5}
    local SIZE=${6}
    local FLAVOR=${7}
    local FLAVOR_MODIFIER=${8}
    local IP=${9}
    local MGMTNETID=${10}
    local MGMTVIF=${11}
    local TENANTNETID=${12}
    local TENANTVIF=${13}
    local TENANTIP=${14}
    local INTERNALNETID=${15}
    local INTERNALVIF=${16}
    local FILE=${17}

    VMNAME_UNDERSCORES=$(echo "${VMNAME}" | sed -e 's/-/_/g')

    local GLANCE_ID=$(get_glance_id ${IMAGE})
    if [ -z "${GLANCE_ID}" ]; then
        echo "No glance image with name: ${IMAGE}"
        return 1
    fi
    NETWORKS=$(get_heat_network_resources_commands ${TENANT} ${VMNAME} ${MGMTNETID} ${TENANTNETID} ${INTERNALNETID})

    if [ "x${BOOT_SOURCE}" == "xglance" ]; then

        cat << EOF > ${FILE}

   ${VMNAME_UNDERSCORES}:
      type: OS::Nova::Server
      properties:
        name: ${VMNAME}
        flavor: ${FLAVOR}
        image: ${IMAGE}
        networks: ${NETWORKS}
EOF

    else
        VOLNAME_UNDERSCORES=$(echo "${VOLNAME}" | sed -e 's/-/_/g')

        cat << EOF > ${FILE}

   ${VOLNAME_UNDERSCORES}:
      type: OS::Cinder::Volume
      properties:
        name: heat_vol_${VOLNAME}
        image: ${IMAGE}
        size: ${SIZE}

   ${VMNAME_UNDERSCORES}:
      type: OS::Nova::Server
      properties:
        name: ${VMNAME}
        flavor: ${FLAVOR}
        block_device_mapping:
        - {device_name: vda, volume_id: { get_resource: ${VOLNAME_UNDERSCORES} } }
        networks: ${NETWORKS}
EOF
    fi

    return 0
}


## Add volume creation to launch file
##
function write_cinder_command()
{
    local NAME=$1
    local IMAGE=$2
    local SIZE=$3
    local BOOT_SOURCE=$4
    local FILE=$5

    # Don't do anything if using glance instead of cinder
    if [ "x${BOOT_SOURCE}" == "xglance" ]; then
        return 0
    fi

    local GLANCE_ID=$(get_glance_id ${IMAGE})
    if [ -z "${GLANCE_ID}" ]; then
        echo "No glance image with name: ${IMAGE}"
        return 1
    fi

    cat << EOF >> ${FILE}
# Allow disk size override for testing
SIZE=\${3:-${SIZE}}

CINDER_ID=\$(cinder ${REGION_OPTION} list | grep "vol-${NAME} " | awk '{print \$2}')
if [ -z "\${CINDER_ID}" ]; then
    cinder ${REGION_OPTION} create --image-id ${GLANCE_ID} --display-name=vol-${NAME} \${SIZE}
    RET=\$?
    if [ \${RET} -ne 0 ]; then
        echo "Failed to create cinder volume 'vol-${NAME}'"
        exit
    fi

    # Wait up to one minute for the volume to be created
    echo "Creating volume 'vol-${NAME}'"
    DELAY=0
    while [ \$DELAY -lt ${CINDER_TIMEOUT} ]; do
        STATUS=\$(cinder ${REGION_OPTION} show vol-${NAME} 2>/dev/null | awk '{ if (\$2 == "status") {print \$4} }')
        if [ \${STATUS} == "downloading" -o \${STATUS} == "creating" ]; then
            DELAY=\$((DELAY + 5))
            sleep 5
        elif [ \${STATUS} == "available" ]; then
            break
        else
            echo "Volume Create Failed"
            exit
        fi
    done

    if [ \${STATUS} == "available" ]; then
        echo "Volume Created"
    else
        echo "Timed out waiting for volume creation"
    fi
fi
CINDER_ID=\$(cinder ${REGION_OPTION} show vol-${NAME} 2>/dev/null | awk '{ if (\$2 == "id") {print \$4} }')

EOF
    return 0
}

## Append commands to create vlan trunks to boot scripts
##
function write_trunk_commands
{
    local FILE=$1
    local INSTANCE=$2
    local INSTANCE_VLANID=$3

        cat << EOF >> ${FILE}
VMNAME=$INSTANCE
NIC_INDEX=0
nova ${REGION_OPTION} show \$VMNAME|grep " network" | awk '{print \$5}'| while read -r ADDRESS; do
    PORT=\$(openstack port list|grep \$ADDRESS)
    PARENTPORT=\`echo \$PORT| awk '{print \$2}'\`
    PARENTMAC=\`echo \$PORT|egrep -o "[[:alnum:]:][[:alnum:]:]*:[[:alnum:]:]**"\`
    PARENTNETWORKID=\`openstack port show \$PARENTPORT -c network_id -f value\`
    PARENTNETWORK=\`openstack network show \$PARENTNETWORKID -c name -f value\`

    SUBPORT_INDEX=0
    for VLAN_NETWORK in \`openstack ${REGION_OPTION} network list -c Name|grep "\${PARENTNETWORK}-"\`; do
        VLAN_NETWORK_NAME=\`echo \$VLAN_NETWORK |egrep -o "[[:alnum:]-]*net[[:alnum:]]*-[[:alnum:]]*"\`
        if [ "x\$VLAN_NETWORK_NAME" == "x" ]; then
            continue
        fi
        VLANID=\`echo \$VLAN_NETWORK|egrep -o "\-[0-9]"|tail -n 1|egrep -o "[0-9]"\`
        if [ "\$VLANID" -ne "$INSTANCE_VLANID" ]; then
            continue
        fi
        if [ "\$SUBPORT_INDEX" -eq "0" ]; then
            openstack ${REGION_OPTION} network trunk create \$VMNAME-trunk\$NIC_INDEX --parent-port \$PARENTPORT
        fi
        openstack ${REGION_OPTION} port create --network \$VLAN_NETWORK_NAME \$VMNAME-trunk\$NIC_INDEX-port\$SUBPORT_INDEX
        echo "source ${HOME}/openrc.admin; openstack ${REGION_OPTION} port set \$VMNAME-trunk\$NIC_INDEX-port\$SUBPORT_INDEX --mac-address \$PARENTMAC"|bash
        openstack ${REGION_OPTION} network trunk set \$VMNAME-trunk\$NIC_INDEX --subport port=\$VMNAME-trunk\$NIC_INDEX-port\$SUBPORT_INDEX,segmentation-type=vlan,segmentation-id=\$VLANID
        SUBPORT_INDEX=\$((SUBPORT_INDEX+1))
    done
    NIC_INDEX=\$((NIC_INDEX+1))
done
EOF
}



## Write the bash commands to launch a VM and assign a floating IP
##
function write_boot_command
{
    local CMD=$1
    local VMNAME=$2
    local FLAVOR=$3
    local FLAVOR_MODIFIER=$4
    local FIPID=$5
    local FILE=$6
    local VLANID=$7

    cat << EOF >> ${FILE}
FLAVOR=\${1:-${FLAVOR}}
FLAVOR_MODIFIER=\${2:-${FLAVOR_MODIFIER}}

if [ ! -z \${FLAVOR_MODIFIER} ]; then
    FLAVOR_MODIFIER=".\${FLAVOR_MODIFIER}"
fi

INFO=\$(nova ${REGION_OPTION} show ${VMNAME} &>> /dev/null)
RET=\$?
if [ \${RET} -ne 0 ]; then
   ${CMD}
   RET=\$?
EOF
    if [ "${VLAN_TRANSPARENT_INTERNAL_NETWORKS}" == "False" ]; then
        write_trunk_commands ${FILE} ${VMNAME} ${VLANID}
    fi

    cat << EOF >> ${FILE}
fi
EOF
    if [ "x${FLOATING_IP}" == "xyes" ]; then
        cat << EOF >> ${FILE}
if [ \${RET} -eq 0 ]; then
   FIXED_ADDRESS=
   PORT_ID=
   RETRY=30
   while [ -z "\${FIXED_ADDRESS}" -a \${RETRY} -ne 0 ]; do
       FIXED_ADDRESS=\$(echo \${INFO} | sed -e 's#^.*192.168#192.168#' -e 's#[, ].*##g')
       PORT_ID=\$(echo "\${INFO}" | grep "nic.*mgmt-net" | grep -Eo "[0-9a-zA-Z]{8}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{4}-[0-9a-zA-Z]{12}")
       if [ -z \${FIXED_ADDRESS} ]; then
           sleep 2
           INFO=\$(nova ${REGION_OPTION} show ${VMNAME})
       fi
       RETRY=\$((RETRY-1))
   done
   if [ -z \${FIXED_ADDRESS} ]; then
       echo "Could not determine fixed address of ${VMNAME}"
       exit 1
   fi
   openstack ${REGION_OPTION} floating ip set ${FIPID} --port \${PORT_ID} --fixed-ip-address \${FIXED_ADDRESS}
   RET=\$?

fi

exit \${RET}
EOF

    else
        cat << EOF >> ${FILE}
exit \${RET}
EOF

    fi

    return 0
}

## Output all wrapper scripts that do not have variable content.
function create_heat_script_files()
{
    info "Writing Heat Scripts to: ${HEATSCRIPT}"

    ## The global file runs each individual tenant file
    GLOBAL_FILENAME=${HEATSCRIPT}
    echo "#!/bin/bash -e" > ${GLOBAL_FILENAME}

    for TENANT in ${TENANTS[@]}; do
        ## The tenant file runs each VMTYPE file for the tenant
        TENANT_FILENAME=${BOOTDIR}/heat_${TENANT}.sh
        TENANT_HEAT_NAME=heat_${TENANT}-instances
        echo "#!/bin/bash -e" > ${TENANT_FILENAME}
        echo "source ${HOME}/openrc.${TENANT}" >> ${TENANT_FILENAME}
        echo "heat stack-create -f ${BOOTDIR}/${TENANT_HEAT_NAME}.yaml ${TENANT_HEAT_NAME}" >> ${TENANT_FILENAME}
        echo "exit 0" >> ${TENANT_FILENAME}
        chmod 755 ${TENANT_FILENAME}

        for INDEX in ${!APPTYPES[@]}; do
            APPTYPE=${APPTYPES[${INDEX}]}
            VMTYPE=${VMTYPES[${INDEX}]}
            ## The tenant APPTYPE file runs one VMTYPE for the tenant
            APPTYPE_FILENAME=${BOOTDIR}/heat_${TENANT}-${VMTYPE}-instances.sh
            APPTYPE_HEAT_NAME=heat_${TENANT}-${VMTYPE}-instances
            echo "#!/bin/bash -e" > ${APPTYPE_FILENAME}
            echo "source ${HOME}/openrc.${TENANT}" >> ${APPTYPE_FILENAME}
            echo "heat stack-create -f ${BOOTDIR}/${APPTYPE_HEAT_NAME}.yaml ${APPTYPE_HEAT_NAME}" >> ${APPTYPE_FILENAME}
            echo "exit 0" >> ${APPTYPE_FILENAME}
            chmod 755 ${APPTYPE_FILENAME}
        done

        echo "${TENANT_FILENAME}" >> ${GLOBAL_FILENAME}
    done

    echo "exit 0" >> ${GLOBAL_FILENAME}
    chmod 755 ${GLOBAL_FILENAME}

    for INDEX in ${!APPTYPES[@]}; do
        APPTYPE=${APPTYPES[${INDEX}]}
        VMTYPE=${VMTYPES[${INDEX}]}
        ## Then APPTYPE file runs all APPTYPE files for all tenants
        APPTYPE_FILENAME=${BOOTDIR}/heat_${VMTYPE}_instances.sh
        echo "#!/bin/bash -e" > ${APPTYPE_FILENAME}

        for TENANT in ${TENANTS[@]}; do
            APPTYPE_HEAT_NAME=heat_${TENANT}-${VMTYPE}-instances
            echo "${BOOTDIR}/${APPTYPE_HEAT_NAME}.sh" >> ${APPTYPE_FILENAME}
        done

        echo "exit 0" >> ${APPTYPE_FILENAME}
        chmod 755 ${APPTYPE_FILENAME}
    done

    return 0
}


## Output all wrapper scripts that do not have variable content.
function create_nova_boot_scripts()
{
    ## Create a wrapper to boot all VM types
    cat << EOF > ${BOOTCMDS}
#!/bin/bash -e
#
VMTYPE=\${1:-"all"}
FLAVOR=\${2:-""}
FLAVOR_MODIFIER=\${3:-""}
EOF

    for INDEX in ${!APPTYPES[@]}; do
        APPTYPE=${APPTYPES[${INDEX}]}
        VMTYPE=${VMTYPES[${INDEX}]}
        APPTYPE_BOOTCMDS=${BOOTDIR}/launch_${VMTYPE}_instances.sh
cat <<EOF >> ${BOOTCMDS}
if [ \${VMTYPE} == "all" -o \${VMTYPE} == "${APPTYPE,,}" ]; then
    ${APPTYPE_BOOTCMDS} \${FLAVOR} \${FLAVOR_MODIFIER}
fi
EOF
     done

cat <<EOF >> ${BOOTCMDS}
exit 0
EOF
    chmod 755 ${BOOTCMDS}

    return 0
}

function get_nova_boot_command_nic_arguments()
{
    local TENANT=$1
    local VMNAME=$2
    local MGMTNETID=$3
    local TENANTNETID=$4
    local INTERNALNETID=$5
    local NICS=""

    MGMTPORTID=$(openstack port list --network ${MGMTNETID} -c ID -c Name -f value | grep -E "${TENANT}.*${VMNAME}" | awk '{print $1}')
    if [ -z ${MGMTPORTID} ]; then
        NICS="${NICS} --nic net-id=${MGMTNETID}"
    else
        NICS="${NICS} --nic port-id=${MGMTPORTID}"
    fi

    if [ "${EXTRA_NICS}" != "yes" ]; then
        echo "${NICS}"
        return 0 
    fi 

    TENANTPORTID=$(openstack port list --network ${TENANTNETID} -c ID -c Name -f value | grep -E "${TENANT}.*${VMNAME}" | awk '{print $1}')
    if [ -z ${TENANTPORTID} ]; then
        NICS="${NICS} --nic net-id=${TENANTNETID}"
    else
        NICS="${NICS} --nic port-id=${TENANTPORTID}"
    fi

    if [ "x${SHARED_TENANT_NETWORKS}" == "xyes" ]; then
        TENANT="${TENANTS[$((1 - ${TENANTNUM}))]}"
    fi 
    INTERNALPORTID=$(openstack port list --network ${INTERNALNETID} -c ID -c Name -f value | grep -m 1 -E "${TENANT}.*${VMNAME}" | awk '{print $1}')
    if [ -z ${INTERNALPORTID} ]; then
        NICS="${NICS} --nic net-id=${INTERNALNETID}"
    else
        NICS="${NICS} --nic port-id=${INTERNALPORTID}"
    fi

    echo "${NICS}"
    return 0
}


## Sets up boot commands for Nova VM instances.  This is purely a convenience
## for lab testing so that the list of networks each VM must be attached to is
## specified in this text file.  Each VM also has user-data which is specific
## to its role and these files are generated and saved for reference.
##
function create_nova_boot_commands()
{
    local VLANID=${FIRSTVLANID}
    local TENANTLIST=${TENANTS[@]}
    local TENANTNUM=0
    local TENANT=""
    local FLAVOR=""
    local NET=0
    local COUNT=0
    local MY_IMAGE=""
    local BOOT_SOURCE="${IMAGE_TYPE}"
    local MY_DISK=""
    local VOLDELAY="no"
    local POLL_ARG="--poll"
    local VMCOUNTER=0
    local TMPHDRFILE="${BOOTDIR}/tmp.hdr"

    test -d ${BOOTDIR} || mkdir -p ${BOOTDIR}

    info "Writing VM boot commands to:  ${BOOTCMDS}"

    ## Create empty boot command files
    for INDEX in ${!APPTYPES[@]}; do
        APPTYPE=${APPTYPES[${INDEX}]}
        VMTYPE=${VMTYPES[${INDEX}]}
        APPTYPE_BOOTCMDS=${BOOTDIR}/launch_${VMTYPE}_instances.sh
        echo "#!/bin/bash -e" > ${APPTYPE_BOOTCMDS}
        chmod 755 ${APPTYPE_BOOTCMDS}
    done

    # Create template heat template header
    cat <<EOF > ${TMPHDRFILE}
heat_template_version: 2013-05-23

description: >
    Creates specified VMs from lab_setup.sh

parameters:

resources:

EOF

    if [ "${SHARED_TENANT_NETWORKS}" == "yes" ]; then
        ## Don't bother generating boot commands for the second tenant since
        ## the system is configured to only support one tenant's VM instances
        ## at a time.
        TENANTLIST=${TENANTS[0]}
    fi

    for TENANT in ${TENANTLIST}; do
        TENANTNET="${TENANT}-net"
        KEYNAME="keypair-${TENANT}"
        TENANT_BOOTCMDS=${BOOTDIR}/launch_${TENANT}_instances.sh
        TENANT_YAMLFILE=${BOOTDIR}/heat_${TENANT}-instances.yaml

        cat <<EOF > ${TENANT_BOOTCMDS}
#!/bin/bash -e
#
VMTYPE=\${1:-"all"}
FLAVOR=\${2:-""}
FLAVOR_MODIFIER=\${3:-""}
EOF
        chmod 755 ${TENANT_BOOTCMDS}

        cp ${TMPHDRFILE} ${TENANT_YAMLFILE}

        # Build the launch and heat commands
        source ${HOME}/openrc.${TENANT}

        if [ "x${FLOATING_IP}" == "xyes" ]; then
            IPLIST=($(openstack ${REGION_OPTION} floating ip list | grep -E "[a-zA-Z0-9]{8}-" | awk '{ print $2; }'))
            if [ ${#IPLIST[@]} -lt ${APPCOUNT} ]; then
                echo "Insufficient number of floating IP addresses"
                return 1
            fi
        else
            IPLIST=""
        fi

        MGMTCOUNTER=0
        NETCOUNTER=0

        for INDEX in ${!APPTYPES[@]}; do
            APPTYPE=${APPTYPES[${INDEX}]}
            VMTYPE=${VMTYPES[${INDEX}]}
            NETTYPE=${NETTYPES[${INDEX}]}
            NIC1_VIF_MODEL=${NIC1_VIF_MODELS[${INDEX}]}
            NIC2_VIF_MODEL=${NIC2_VIF_MODELS[${INDEX}]}
            APP_VARNAME=${APPTYPE}APPS
            IMAGE_VARNAME=${APPTYPE}_IMAGE
            FLAVOR_VARNAME=${APPTYPE}FLAVOR
            APPTYPE_YAMLFILE=${BOOTDIR}/heat_${TENANT}-${VMTYPE}-instances.yaml
            APPTYPE_BOOTCMDS=${BOOTDIR}/launch_${VMTYPE}_instances.sh

            cp ${TMPHDRFILE} ${APPTYPE_YAMLFILE}

            APPS=(${!APP_VARNAME})
            VMCOUNTER=1
            for INDEX in ${!APPS[@]}; do
                ENTRY=${APPS[${INDEX}]}
                DATA=(${ENTRY//|/ })
                NUMVMS=${DATA[0]}
                log "  Adding ${APPTYPE} VMs ${ENTRY}"

                MY_IMAGE=${!IMAGE_VARNAME}
                MY_DISK=${IMAGE_SIZE}
                FLAVOR=${!FLAVOR_VARNAME}
                BOOT_SOURCE=${IMAGE_TYPE}
                VOLDELAY="no"
                POLL_ARG="--poll"
                for KEYVALUE in ${DATA[@]}; do
                    KEYVAL=(${KEYVALUE//=/ })
                    if [ "x${KEYVAL[0]}" == "ximage" -o "x${KEYVAL[0]}" == "ximageqcow2" ]; then
                        MY_IMAGE=${KEYVAL[1]}
                    elif [ "x${KEYVAL[0]}" == "xdisk" ]; then
                        MY_DISK=${KEYVAL[1]}
                    elif [ "x${KEYVAL[0]}" == "xflavor" ]; then
                        FLAVOR=${KEYVAL[1]}
                    elif [ "x${KEYVAL[0]}" == "xnopoll" ]; then
                        POLL_ARG=""
                    elif [ "x${KEYVAL[0]}" == "xglance" ]; then
                        BOOT_SOURCE="glance"
                    fi
                done

                for I in $(seq 1 ${NUMVMS}); do
                    ## Determine actual network number and host number for this VM
                    NETNUMBER=$((NETCOUNTER / ${VMS_PER_NETWORK}))
                    HOSTNUMBER=$((NETCOUNTER % ${VMS_PER_NETWORK}))

                    if [ "x${REUSE_NETWORKS}" != "xyes" -a "x${ROUTED_TENANT_NETWORKS}" != "xyes" ]; then
                        VLANID=$(((NETNUMBER % ${MAXVLANS}) + ${FIRSTVLANID}))
                    fi

                    if [ ${APPCOUNT} -ge ${MGMTNETS} ]; then
                        ## Spread the VM instances evenly over the number of mgmt networks.
                        MGMTNETNUMBER=$((MGMTCOUNTER / (${APPCOUNT} / ${MGMTNETS})))
                    else
                        MGMTNETNUMBER=0
                    fi
                    MGMTNET=$(get_mgmt_network_name ${TENANT}-mgmt-net ${MGMTNETNUMBER})
                    MGMTNETID=$(get_network_id ${MGMTNET})
                    if [ -z "${MGMTNETID}" ]; then
                        echo "Unable to find management network: ${MGMTNET}"
                        return 1
                    fi

                    TENANTNETID=$(get_network_id ${TENANTNET}${NETNUMBER})
                    INTERNALNETID=$(get_internal_network_id ${TENANTNUM} ${NETNUMBER} ${VLANID})
                    INTERNALNETNAME=$(get_internal_network_name ${TENANTNUM} ${NETNUMBER})
                    if [ "${EXTRA_NICS}" == "yes" ]; then
                        TENANTMTU=$(get_network_mtu ${TENANTNETID})
                        INTERNALMTU=$(get_network_mtu ${INTERNALNETID})
                    else
                        TENANTMTU=1500
                        INTERNALMTU=1500
                    fi
                    VMNAME="${TENANT}-${VMTYPE}${VMCOUNTER}"
                    USERDATA=$(create_userdata ${VMNAME} ${VMTYPE} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU} ${MY_IMAGE})
                    IMAGEARG=$(create_image_args ${VMNAME} ${MY_IMAGE} ${BOOT_SOURCE})
                    FLAVOR_MODIFIER=$(get_flavor_modifier ${TENANTNUM} ${VMCOUNTER})
                    TENANTIPADDR=$(get_network_ip_address ${NETNUMBER} ${HOSTNUMBER} ${TENANTNUM})
                    TENANTIPARG=$(get_network_ip ${NETNUMBER} ${HOSTNUMBER} ${TENANTNUM})
                    CONFIGDRIVE_ARGS=""
                    if [ "${CONFIG_DRIVE}" == "yes" ]; then
                        CONFIGDRIVE_ARGS="--config-drive=true"
                    fi
                    NICS=$(get_nova_boot_command_nic_arguments ${TENANT} ${VMTYPE}${VMCOUNTER} ${MGMTNETID} ${TENANTNETID} ${INTERNALNETID})
                    CMD="nova ${REGION_OPTION} boot ${POLL_ARG} ${CONFIGDRIVE_ARGS} --key-name=${KEYNAME} --flavor=\${FLAVOR}\${FLAVOR_MODIFIER} \
${NICS} \
--user-data ${USERDATA} \
${IMAGEARG} \
${VMNAME}"
                    # Create a file to store the VM boot commands which returns the name in "FILENAME"
                    create_boot_command_file ${TENANT} ${VMNAME} FILENAME

                    # Write volume create in case volume creation delays (or volume accidentally deleted
                    write_cinder_command ${VMNAME} "${MY_IMAGE}" "${MY_DISK}" "${BOOT_SOURCE}" ${FILENAME}

                    # Write the actual boot command
                    write_boot_command "${CMD}" ${VMNAME} "${FLAVOR}" "${FLAVOR_MODIFIER}" "${IPLIST}" ${FILENAME} ${VLANID}

                    # Add the execution of FILENAME to the APPTYPE wrapper script
                    echo "${FILENAME} \$@" >> ${APPTYPE_BOOTCMDS}

                    # Add the execution of FILENAME to the TENANT wrapper script
                    cat << EOF >> ${TENANT_BOOTCMDS}
if [ \${VMTYPE} == "all" -o \${VMTYPE} == "${APPTYPE,,}" ]; then
    ${FILENAME} \${FLAVOR} \${FLAVOR_MODIFIER}
fi
EOF

                    # Create a heat yaml file for this VM instance
                    create_heat_yaml_file ${TENANT} ${VMNAME} YAMLFILE

                    # Write the heat resources out to a temporary file
                    TMP_YAMLFILE=${BOOTDIR}/tmp.yaml
                    write_heat_resource_commands "${TENANT}" "${VMNAME}" "vol-${VMNAME}" "${MY_IMAGE}" "${BOOT_SOURCE}" "${MY_DISK}" "${FLAVOR}" "${FLAVOR_MODIFIER}" "${IPLIST}" "${MGMTNETID}" "${MGMT_VIF_MODEL}" "${TENANTNETID}" "${NIC1_VIF_MODEL}" "${TENANTIPADDR}" "${INTERNALNETID}" "${NIC2_VIF_MODEL}" "${TMP_YAMLFILE}"

                    # Write the heat userdata to a temporary file.
                    append_heat_userdata ${VMNAME} ${VMTYPE} ${NETTYPE} ${TENANTNUM} ${NETNUMBER} ${HOSTNUMBER} ${VLANID} ${TENANTMTU} ${INTERNALMTU} ${TMP_YAMLFILE} ${MY_IMAGE}
                    # Append the contents of the newly created temporary file
                    # to each of the yaml files (i.e., the VM file, the tenant
                    # file, and the apptype file
                    #
                    cat ${TMP_YAMLFILE} >> ${YAMLFILE}
                    cat ${TMP_YAMLFILE} >> ${TENANT_YAMLFILE}
                    cat ${TMP_YAMLFILE} >> ${APPTYPE_YAMLFILE}
                    rm -f ${TMP_YAMLFILE}

                    ## Create a wrapper to launch the single VM heat stack
                    cat << EOF > ${BOOTDIR}/heat_${VMNAME}.sh
#!/bin/bash -e
source /home/wrsroot/openrc.${TENANT}
heat stack-create -f ${YAMLFILE} heat_${VMNAME}
exit 0
EOF
                    chmod 755 ${BOOTDIR}/heat_${VMNAME}.sh

                    if [ "x${FLOATING_IP}" == "xyes" ]; then
                        IPLIST=(${IPLIST[@]:1})
                    fi

                    NETCOUNTER=$((NETCOUNTER+1))
                    MGMTCOUNTER=$((MGMTCOUNTER+1))
                    VMCOUNTER=$((VMCOUNTER+1))
                done

		if [ "x${REUSE_NETWORKS}" == "xyes" ]; then
                    NETCOUNTER=0
		fi
            done
        done

        TENANTNUM=$((TENANTNUM + 1))
        echo "exit 0" >> ${TENANT_BOOTCMDS}
    done

    ## Create the wrapper boot scripts
    create_nova_boot_scripts

    return 0
}

function setup_openstack_gnp_oam_firewall_overrides()
{
    if [ -n "${AVAIL_CONTROLLER_NODES}" ]; then
        echo "Setting up Openstack Global Network OAM firewall overrides"
        log_command "kubectl apply -f openstack-gnp-oam.yaml"
        if [ ${RET} -ne 0 ]; then
            echo "Failed setting up Openstack Global Network OAM firewall overrides"
            return ${RET}
        fi
    fi
    return 0
}

function setup_providernet_tenants_quota_credentials()
{
    if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xsubcloud" ]; then
        add_tenants
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to add tenants, ret=${RET}"
            exit ${RET}
        fi
    fi

    ## Cache the tenantid values
    ADMINID=$(get_tenant_id admin)
    TENANT1ID=$(get_tenant_id ${TENANT1})
    TENANT2ID=$(get_tenant_id ${TENANT2})

    create_credentials
    RET=$?
    if [ ${RET} -ne 0 ]; then
        echo "Failed to create credentials, ret=${RET}"
        exit ${RET}
    fi

    if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xsubcloud" ]; then
        set_quotas
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to set quotas, ret=${RET}"
            exit ${RET}
        fi
    fi

    #source ${OPENRC}
    if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xsubcloud" ]; then
        if [ "x${CONVERTED_LAB}" != "xyes" ]; then
            if [ ${GROUPNO} -eq 0 ]; then
                setup_flavors
                RET=$?
                if [ ${RET} -ne 0 ]; then
                    echo "Failed to setup flavors, ret=${RET}"
                    exit ${RET}
                fi
            fi

            create_custom_flavors
            RET=$?
            if [ ${RET} -ne 0 ]; then
                echo "Failed to create custom flavors, ret=${RET}"
                exit ${RET}
            fi
        fi
    fi

    if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xsubcloud" ]; then
        setup_keys
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to setup keys, ret=${RET}"
            exit ${RET}
        fi
    fi

    return 0

}

##Wait for applicatin apply to complete
function wait_for_application_apply()
{
    local APPLICATION_CONFIGURED_TIMEOUT=3600
    local APPLICATION_CONFIGURED_DELAY=0
    while [[ $APPLICATION_CONFIGURED_DELAY -lt $APPLICATION_CONFIGURED_TIMEOUT ]]; do
        app_info=$(system application-list ${CLI_NOWRAP} | grep stx-openstack)
        app_status=$(echo ${app_info}| awk '{print $10}')
        #app_task=$(echo ${app_info}| awk '{print $10}')

        if [[ ${app_status} == "apply-failed" ]]; then
            echo "Application  stx-openstack : apply failed"
            return 1
        fi

        if [[ ${app_status} == *"applying"* ]]; then
            log "Waiting for application to become applied info: stx-openstack"
            sleep 30
            APPLICATION_CONFIGURED_DELAY=$((APPLICATION_CONFIGURED_DELAY + 10))
        else
            log "stx-openstack application: apply complete"
            break
        fi
    done

    if [[ APPLICATION_CONFIGURED_DELAY -eq APPLICATION_CONFIGURED_TIMEOUT ]]; then
        echo "ERROR: timed out waiting for stx-openstack to become applied"
        return 1
    fi
    return 0
}

wait_for_nodes_to_be_ready()
{
    local NODES_READY_TIMEOUT=2400
    local NODES_READY_DELAY=0
    local AVAIL_NODES=$(system host-list ${CLI_NOWRAP} | awk ' {if ($6 != "storage" && $12 == "available") print $4;}')
    local NOT_READY_NODES=""
    if [ -z "${AVAIL_NODES}" ]; then
       return 0
    fi
    info "Waiting for all nodes to be Ready...."
    while [ "$NODES_READY_DELAY" -lt "$NODES_READY_TIMEOUT" ]; do
        for NODE in ${AVAIL_NODES}; do
            local node_status=$(kubectl get nodes ${NODE} | awk ' {if ($2 != "STATUS") print $2}')
            if [ "${node_status}" != "Ready" ]; then
                NOT_READY_NODES+=${NODE}" "
            fi
        done
        if [ -z "${NOT_READY_NODES}" ]; then
            return 0
        else
            log "Waiting for ${NOT_READY_NODES} to become Ready"
            sleep 10
            NODES_READY_DELAY=$((NODES_READY_DELAY + 10))
        fi
        AVAIL_NODES=${NOT_READY_NODES}
        NOT_READY_NODES=""
    done
     
    if [ "${NODES_READY_DELAY}" -eq "${NODES_READY_TIMEOUT}" ]; then
        echo "ERROR: timed out waiting for ${AVAIL_NODES}  to become Ready"
        return 1
    fi
    return 0
}


wait_for_platform_integration_application()
{
    local PLATFORM_APPLICATION_CONFIGURED_TIMEOUT=1200
    local PLATFORM_APPLICATION_CONFIGURED_DELAY=0
    while [[ $PLATFORM_APPLICATION_CONFIGURED_DELAY -lt $PLATFORM_APPLICATION_CONFIGURED_TIMEOUT ]]; do
        local app_info=$(system application-list ${CLI_NOWRAP} | grep platform-integration-manifest)
        local app_status=$(echo ${app_info}| awk '{print $10}')

        if [[ ${app_status} == "upload-failed" || ${app_status} == "apply-failed"  ]]; then
            log "Application platform-integration-manifest: upload/apply failed"
            return 1
        fi

        # Apply app if it's uploaded or apply-failed
        #if [[ ${app_status} == *"uploaded"* ]]; then
        #    info "Applying platform-integration-manifest application"
        #    log_command "system application-apply platform-integ-apps"
        #    RET=$?
        #    if [[ ${RET} -ne 0 ]]; then
        #        exit ${RET}
        #    fi
        #fi
        if [[ ${app_status} == *"uploading"* || ${app_status} == *"uploaded"* || ${app_status} == *"applying"* ]]; then
            log "Waiting for application to become uploaded/applied: platform-integration-manifest"
            sleep 10
            PLATFORM_APPLICATION_CONFIGURED_DELAY=$((PLATFORM_APPLICATION_CONFIGURED_DELAY + 10))
        elif [[ ${app_status} == *"applied"* ]]; then
            log "platform-integration-manifest application: apply completed"
            return 0
        else
           echo "ERROR: Application platform-integration-manifest in unexpected state: $app_status"
                return 1
        fi
    done

    if [[ ${PLATFORM_APPLICATION_CONFIGURED_DELAY} -eq ${PLATFORM_APPLICATION_CONFIGURED_TIMEOUT} ]]; then
        echo "ERROR: timed out waiting for platform-integration-manifest  to become applied"
        return 1
    fi
    return 0
}

# Wait for application upload to complete
function wait_for_application_upload()
{
    local APPLICATION_CONFIGURED_TIMEOUT=600
    local APPLICATION_CONFIGURED_DELAY=0
    while [[ $APPLICATION_CONFIGURED_DELAY -lt $APPLICATION_CONFIGURED_TIMEOUT ]]; do
        app_info=$(system application-list ${CLI_NOWRAP} | grep stx-openstack)
        app_status=$(echo ${app_info}| awk '{print $10}')

        if [[ ${app_status} == "upload-failed" ]]; then
            log "Application stx-openstack: upload failed"
            return 1
        fi

        if [[ ${app_status} == *"uploading"* ]]; then
            log "Waiting for application to become uploaded: stx-openstack"
            sleep 10
            APPLICATION_CONFIGURED_DELAY=$((APPLICATION_CONFIGURED_DELAY + 10))
        else
            log "stx-openstack application: upload completed"
            break
        fi
    done

    if [[ APPLICATION_CONFIGURED_DELAY -eq APPLICATION_CONFIGURED_TIMEOUT ]]; then
        echo "ERROR: timed out waiting for stx-openstack to become uploaded"
        return 1
    fi
    return 0
}

# Upload application (helm-charts) and apply application
function setup_kube_pods()
{
    if [[ "$K8S_ENABLED" != "yes" ]]; then
        return 0
    fi

    if is_stage_complete "openstack_deployment"; then
        info "Skipping Openstack app deployment configuration; already done"
        return 0
    fi

    STX_OPENSTACK_CHARTS="helm-charts-manifest.tgz"
        
    # Add DNS Cluster, might need to remove later
    # DNS_EP=$(kubectl describe svc -n kube-system kube-dns | awk /IP:/'{print $2}')
    # log_command "system dns-modify nameservers="$DNS_EP,8.8.8.8""
    # RET=$?
    # log_command "ceph osd pool ls | xargs -i ceph osd pool set {} size 1"
    
    set +e
    app_info=$(system application-list ${CLI_NOWRAP} | grep stx-openstack)
    app_status=$(echo ${app_info}| awk '{print $10}')
    set -e
    echo "app status is: ${app_status}"

    # Return right away if applied
    if [[ ${app_status} == *"applied"* ]]; then
        log "Application already applied"
        stage_complete "openstack_deployment"
        return 0
    fi

    # Check if platform-integration-manifest is applied
    set +e
    plat_app_info=$(system application-list ${CLI_NOWRAP} | grep platform-integration-manifest)
    plat_app_status=$(echo ${plat_app_info}| awk '{print $10}')
    set -e
    echo "platform-integration-manifest status is: ${plat_app_status}"

    # Upload app if it has not been uploaded or upload-failed
    if [[ ${plat_app_status} == *"applying"* || ${plat_app_status} == *"uploaded"* ]]; then
        info "Waiting for platform-integration-manifest  application"
        wait_for_platform_integration_application
        RET=$?
        if [[ ${RET} -ne 0 ]]; then
            exit ${RET}
        fi
        plat_app_status=applied
    fi

    # Return if platform-integration-manifest is not in  applied state
    if [[ ${plat_app_status} != *"applied"* ]]; then
        log "The platform-integration-manifest app is not applied; cannot apply ${STX_OPENSTACK_CHARTS}"
        return 1
    fi
    
    # wait for all nodes to be ready
    wait_for_nodes_to_be_ready
    RET=$?
    if [[ ${RET} -ne 0 ]]; then
        exit ${RET}
    fi

    # Upload app if it has not been uploaded or upload-failed
    if [[ ${app_status} != *"appl"* && ${app_status} != *"uploaded"* ]]; then
        info "Uploading stx-openstack application"
        log_command "system application-upload ${STX_OPENSTACK_CHARTS}"
        wait_for_application_upload
        RET=$?
        if [[ ${RET} -ne 0 ]]; then
            exit ${RET}
        fi
        app_status=uploaded
    fi

    # DPDK apps running in a VM need the cpu model set accordingly.
    # Note: this can probably be removed once https://blueprints.launchpad.net/nova/+spec/cpu-model-selection
    # is implemented and merged
    if [ -z "${DPDKAPPS//[0-9]}" ] && [[ "${DPDKAPPS}" -gt 0 ]]; then
        info "Setting cpu model override for DPDK VM applications"
        log_command "system helm-override-update stx-openstack nova openstack --set conf.nova.libvirt.cpu_mode=custom --set conf.nova.libvirt.cpu_model=SandyBridge"
    fi

    # Apply app if it's uploaded or apply-failed
    if [[ ${app_status} != *"applying"* ]]; then
        info "Applying stx-openstack application"
        log_command "system application-apply stx-openstack"
        RET=$?
        if [[ ${RET} -ne 0 ]]; then
            exit ${RET}
        fi
    fi

    wait_for_application_apply
    RET=$?
    if [[ ${RET} -ne 0 ]]; then
        exit ${RET}
    fi

    stage_complete "openstack_deployment"
    return 0
}

# Check URL connection
function check_url_status()
{
    local URL=$1
    if [ -z "${URL}" ]; then
        echo "$URL is empty"
        return 1
    fi
    local TOTAL_ATTEMPTS=3
    local attempts=0
    while [ ${attempts} -lt  ${TOTAL_ATTEMPTS} ]; do

        local status="$(timeout 5s curl -Is ${URL} | head -1)"
        if [ "${status:9:3}" == "200" ]; then
            return 0
        else
           attempt= $((attempts + 1))
           sleep 2
        fi
    done
    return 1

}

if [ -f "${STATUS_FILE}" ]; then
    rm -f ${STATUS_FILE}
fi

#TODO: CONFIG
log "============================================================================"
log "Starting lab setup (${CONFIG_FILES}): $(date)"
declare -p >> ${LOG_FILE}
log "============================================================================"

echo "Checking for required files"
check_required_files
RET=$?
if [ ${RET} -ne 0 ]; then
    echo "Failed to check required files, ret=${RET}"
    exit ${RET}
fi

setup_openstack_gnp_oam_firewall_overrides
RET=$?
if [ ${RET} -ne 0 ]; then
  echo "Failed to set Opnestack globalnetworkpolicy configuration , ret=${RET}"
  exit ${RET}
fi

FILE=.no_openstack_install
if [ -f ${FILE} ]; then
    echo "File to stop exist, if you want to continue, remove .no_openstack_install file and run."
    exit 0
fi

###Need to bring up the pods here for kubernetes:

setup_kube_pods
RET=$?
if [ ${RET} -ne 0 ]; then
    echo "Failed to apply application, ret=${RET}"
    exit ${RET}
fi
if [ "$K8S_ENABLED" == "yes" ]; then
    unset OS_AUTH_URL
    export OS_AUTH_URL=${K8S_URL}
    setup_providernet_tenants_quota_credentials
    add_network_segment_ranges
fi

if [ "x${CONVERTED_LAB}" != "xyes" ]; then
    if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xsubcloud" ]; then
        setup_glance_images
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to setup images, ret=${RET}"
            exit ${RET}
        fi
    fi
    if [ "x${IMAGE_TYPE}" == "xcinder" ]; then
        if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xsubcloud" ]; then            
            set_cinder_quotas
        fi
        if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xcontroller" ]; then
            setup_cinder_volumes
            RET=$?
            if [ ${RET} -ne 0 ]; then
                echo "Failed to setup volumes, ret=${RET}"
                exit ${RET}
            fi
        fi
    fi
else
    if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xsubcloud" ]; then
        set_cinder_quotas
    fi
fi

if [ "x${CONVERTED_LAB}" != "xyes" ]; then
    if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xcontroller" ]; then
        # This is an AVS specific feature
        if [ "${VSWITCH_TYPE}" == "avs" ]; then
            add_qos_policies
            RET=$?
            if [ ${RET} -ne 0 ]; then
                echo "Failed to add network qos policies, ret=${RET}"
                exit ${RET}
            fi
         fi

        setup_internal_networks
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to setup infrastructure networks, ret=${RET}"
            exit ${RET}
        fi

        setup_management_networks
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to setup management networks, ret=${RET}"
            exit ${RET}
        fi

        setup_ixia_networks
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to setup ixia networks, ret=${RET}"
            exit ${RET}
        fi

        setup_tenant_networks
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to setup tenant networks, ret=${RET}"
            exit ${RET}
        fi

        setup_management_ports
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to create management ports, ret=${RET}"
            exit ${RET}
        fi

        setup_tenant_ports
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to create tenant ports, ret=${RET}"
            exit ${RET}
        fi

        setup_internal_ports
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to create internal ports, ret=${RET}"
            exit ${RET}
        fi

        if [ "x${FLOATING_IP}" == "xyes" ]; then
            setup_floating_ips
            RET=$?
            if [ ${RET} -ne 0 ]; then
                echo "Failed to setup floating IP addresses, ret=${RET}"
                exit ${RET}
            fi
        fi
    fi
    
    ## return to admin context
    source ${OPENRC}
    if [ "x${DISTRIBUTED_CLOUD_ROLE}" != "xcontroller" ]; then
     
        if [ -d "${BOOTDIR}" ]; then
            ## Start with a clean directory to start heat/launch scripts
            rm -f ${BOOTDIR}/*
        fi

        echo "Writing Heat Scripts to: ${HEATSCRIPT}"
        create_heat_script_files
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to create heat script files, ret=${RET}"
            exit ${RET}
        fi

        echo "Writing VM boot commands to:  ${BOOTCMDS}"
        create_nova_boot_commands
        RET=$?
        if [ ${RET} -ne 0 ]; then
            echo "Failed to create nova boot commands, ret=${RET}"
            exit ${RET}
        fi
    else
        echo ""
        echo "Launch heat stacks to complete lab setup"
        echo ""
    fi
fi

source ${OPENRC}

## return to admin context
source ${OPENRC}

echo "CONFIG_FILE=${CONFIG_FILES}" > ${STATUS_FILE}
echo "CONFIG_FILE=${CONFIG_FILES}" > ${GROUP_STATUS}
echo "Done"

exit 0
