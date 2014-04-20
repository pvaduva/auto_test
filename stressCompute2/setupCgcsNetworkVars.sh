source /etc/nova/openrc

PUBLICNETSUBNET=192.168.101.0/24
PRIVATENETSUBNET=192.168.201.0/24
GATEWAY=192.168.1.1
EXTERNALNETSUBNET=192.168.1.0/24

NEUTRONVARS=/tmp/neutron_vars.txt

ADMINID=`keystone tenant-list | grep admin | awk '{print $2}'`
echo "ADMINID: $ADMINID"

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
PUBLICNETID=`neutron net-list | grep ${PUBLICNET} | awk '{print $2}'`
PRIVATENETID=`neutron net-list | grep ${PRIVATENET} | awk '{print $2}'`
INTERNALNETID=`neutron net-list | grep ${INTERNALNET} | awk '{print $2}'`
EXTERNALNETID=`neutron net-list | grep ${EXTERNALNET} | awk '{print $2}'`
PRIVATEROUTERID=`neutron router-list | grep ${PRIVATEROUTER} | awk '{print $2}'`
PUBLICROUTERID=`neutron router-list | grep ${PUBLICROUTER} | awk '{print $2}'`

