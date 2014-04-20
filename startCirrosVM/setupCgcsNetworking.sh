source /etc/nova/openrc

#
# This cgcs network setups script is copied from:
# http://twiki.wrs.com/PBUeng/HowToConfigureControllerAndComputeNodes
# r40 - 09 Jan 2014 - 20:30:21 - DonPenney

# 25jan14 ccw  Initial creation

ADMINID=`keystone tenant-list | grep admin | awk '{print $2}'`
PUBLICNET='public-net0'
PRIVATENET='private-net0'
INTERNALNET='internal-net0'
EXTERNALNET='external-net0'
PUBLICSUBNET='public-subnet0'
PRIVATESUBNET='private-subnet0'
INTERNALSUBNET='internal-subnet0'
EXTERNALSUBNET='external-subnet0'
PUBLICROUTER='public-router0'
PRIVATEROUTER='private-router0'

neutron net-create --tenant-id ${ADMINID} --provider:network_type=vlan --provider:physical_network=physnet0 --provider:segmentation_id=600 ${PUBLICNET}
neutron net-create --tenant-id ${ADMINID} --provider:network_type=vlan --provider:physical_network=physnet1 --provider:segmentation_id=700 ${PRIVATENET}
neutron net-create --tenant-id ${ADMINID} --provider:network_type=vlan --provider:physical_network=physnet1 --provider:segmentation_id=701 ${INTERNALNET}
neutron net-create --tenant-id ${ADMINID} --provider:network_type=vlan --provider:physical_network=physnet0 --provider:segmentation_id=10 --router:external ${EXTERNALNET}
PUBLICNETID=`neutron net-list | grep ${PUBLICNET} | awk '{print $2}'`
PRIVATENETID=`neutron net-list | grep ${PRIVATENET} | awk '{print $2}'`
INTERNALNETID=`neutron net-list | grep ${INTERNALNET} | awk '{print $2}'`
EXTERNALNETID=`neutron net-list | grep ${EXTERNALNET} | awk '{print $2}'`
neutron subnet-create --tenant-id ${ADMINID} --name ${PUBLICSUBNET} ${PUBLICNET} 192.168.101.0/24
neutron subnet-create --tenant-id ${ADMINID} --name ${PRIVATESUBNET} ${PRIVATENET} 192.168.201.0/24
neutron subnet-create --tenant-id ${ADMINID} --name ${INTERNALSUBNET} --no-gateway ${INTERNALNET} 10.10.0.0/24
neutron subnet-create --tenant-id ${ADMINID} --name ${EXTERNALSUBNET} --gateway 192.168.1.1 --disable-dhcp ${EXTERNALNET} 192.168.1.0/24
neutron router-create ${PUBLICROUTER}
neutron router-create ${PRIVATEROUTER}
PRIVATEROUTERID=`neutron router-list | grep ${PRIVATEROUTER} | awk '{print $2}'`
PUBLICROUTERID=`neutron router-list | grep ${PUBLICROUTER} | awk '{print $2}'`
neutron router-gateway-set ${PUBLICROUTERID} ${EXTERNALNETID}
neutron router-gateway-set ${PRIVATEROUTERID} ${EXTERNALNETID}
neutron router-interface-add ${PUBLICROUTER} ${PUBLICSUBNET}
neutron router-interface-add ${PRIVATEROUTER} ${PRIVATESUBNET}

