source /etc/nova/openrc

#
# This cgcs network setups script is copied from:
# http://twiki.wrs.com/PBUeng/HowToConfigureControllerAndComputeNodes
# r40 - 09 Jan 2014 - 20:30:21 - DonPenney

# 25jan14 ccw  Initial creation
#
# WASSP will execute the following, ex:
# ip1-4
# ~/bin/setupCgcsNetworking.sh  "192.168.101.0/24"   "192.168.201.0/24"   "192.168.1.0/24" "10.10.0.0/24" "192.168.1.1" "10.10.1.0/24" "10-10" "600-631" "700-763" "192.168.101.2" "192.168.101.30" "192.168.201.2" "192.168.201.30"
# hp380
# ~/bin/setupCgcsNetworking.sh  "192.168.109.0/24"   "192.168.209.0/24"   "192.168.9.0/24" "10.10.0.0/24" "192.168.9.1" "10.10.1.0/24" "10-10" "472-535" "536-567" "192.168.109.2" "192.168.109.30" "192.168.209.2" "192.168.209.30"

PUBLICNETSUBNET=192.168.107.0/24
PRIVATENETSUBNET=192.168.207.0/24
EXTERNALNETSUBNET=192.168.7.0/24

EXTERNALGATEWAY=192.168.1.1

vlanExternal=10-10
vlanPhysnet0=600-631
vlanPhysnet1=700-763

PUBLICNETSUBNET=${1}
PRIVATENETSUBNET=${2}
EXTERNALNETSUBNET=${3}
INTERNALNETSUBNET=${4}
EXTERNALGATEWAY=${5}
TAGGEDNETSUBNET=${6}
vlanExternal=${7}
vlanPhysnet0=${8}
vlanPhysnet1=${9}
POOLSTARTPUB=${10}
POOLENDPUB=${11}
POOLSTARTPRIV=${12}
POOLENDPRIV=${13}

ADMINID=`keystone tenant-list | grep admin | awk '{print $2}'`
PHYSNET0='physnet0'
PHYSNET1='physnet1'
PUBLICNET='public-net0'
PRIVATENET='private-net0'
INTERNALNET='internal-net0'
EXTERNALNET='external-net0'
PUBLICSUBNET='public-subnet0'
PRIVATESUBNET='private-subnet0'
INTERNALSUBNET='internal-subnet0'
TAGGEDSUBNET='tagged-subnet0'
EXTERNALSUBNET='external-subnet0'
PUBLICROUTER='public-router0'
PRIVATEROUTER='private-router0'

### the issues is right here, looks like the wiki has changed 
neutron providernet-create ${PHYSNET0} --type vlan
neutron providernet-create ${PHYSNET1} --type vlan
neutron providernet-range-create ${PHYSNET0} --name ${PHYSNET0}-a --range $vlanPhysnet0
neutron providernet-range-create ${PHYSNET0} --name ${PHYSNET0}-b --range $vlanExternal
neutron providernet-range-create ${PHYSNET1} --name ${PHYSNET1}-a --range $vlanPhysnet1


neutron net-create --tenant-id ${ADMINID} --provider:physical_network=${PHYSNET0} --provider:segmentation_id=10 --router:external ${EXTERNALNET}
neutron net-create --tenant-id ${ADMINID} --provider:physical_network=${PHYSNET0} ${PUBLICNET}
neutron net-create --tenant-id ${ADMINID} --provider:physical_network=${PHYSNET1} ${PRIVATENET}
neutron net-create --tenant-id ${ADMINID} ${INTERNALNET}

PUBLICNETID=`neutron net-list | grep ${PUBLICNET} | awk '{print $2}'`
PRIVATENETID=`neutron net-list | grep ${PRIVATENET} | awk '{print $2}'`
INTERNALNETID=`neutron net-list | grep ${INTERNALNET} | awk '{print $2}'`
EXTERNALNETID=`neutron net-list | grep ${EXTERNALNET} | awk '{print $2}'`

# to work around nat-box limitations: http://jira.wrs.com/browse/CGTS-570  setting explicit DHCP allocation-pool
echo "executing: neutron subnet-create --tenant-id ${ADMINID} --name ${PUBLICSUBNET} --allocation-pool start=${POOLSTARTPUB},end=${POOLENDPUB}  ${PUBLICNET} ${PUBLICNETSUBNET}"
neutron subnet-create --tenant-id ${ADMINID} --name ${PUBLICSUBNET} --allocation-pool start=${POOLSTARTPUB},end=${POOLENDPUB}  ${PUBLICNET} ${PUBLICNETSUBNET}
sleep 5
echo "executing: neutron subnet-create --tenant-id ${ADMINID} --name ${PRIVATESUBNET} --allocation-pool start=${POOLSTARTPRIV},end=${POOLENDPRIV}  ${PRIVATENET} ${PRIVATENETSUBNET}"
neutron subnet-create --tenant-id ${ADMINID} --name ${PRIVATESUBNET} --allocation-pool start=${POOLSTARTPRIV},end=${POOLENDPRIV}  ${PRIVATENET} ${PRIVATENETSUBNET}
sleep 5

neutron subnet-create --tenant-id ${ADMINID} --name ${INTERNALSUBNET} --no-gateway ${INTERNALNET} $INTERNALNETSUBNET
neutron subnet-create --tenant-id ${ADMINID} --name ${TAGGEDSUBNET} --no-gateway --vlan-id 1 ${INTERNALNET} $TAGGEDNETSUBNET
neutron subnet-create --tenant-id ${ADMINID} --name ${EXTERNALSUBNET} --gateway ${EXTERNALGATEWAY} --disable-dhcp ${EXTERNALNET} $EXTERNALNETSUBNET

neutron router-create ${PUBLICROUTER}
neutron router-create ${PRIVATEROUTER}
PRIVATEROUTERID=`neutron router-list | grep ${PRIVATEROUTER} | awk '{print $2}'`
PUBLICROUTERID=`neutron router-list | grep ${PUBLICROUTER} | awk '{print $2}'`
neutron router-gateway-set ${PUBLICROUTERID} ${EXTERNALNETID}
neutron router-gateway-set ${PRIVATEROUTERID} ${EXTERNALNETID}
neutron router-interface-add ${PUBLICROUTER} ${PUBLICSUBNET}
neutron router-interface-add ${PRIVATEROUTER} ${PRIVATESUBNET}

