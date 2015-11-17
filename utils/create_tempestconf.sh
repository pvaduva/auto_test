#!/bin/bash
# invocation example:
# /root/bin/create_tempestconf.sh 128.224.150.11 cgcs li69nux 100 200 100 200 tenant1-net1 tenant1-router

NATIP=${1}
NATUSER=${2}
NATPASS=${3}
compute0=${4}
compute1=${5}
controller0=${6}
controller1=${7}
PUBLIC_NETWORK=${8}
PUBLIC_ROUTER=${9}
ADMINPASS=${10}
WRSPASS=${11}
#Alter  tempest.conf  based on runtime parameters configured during: setupCgcsNetworking

source /etc/nova/openrc
MGMT_IP=`system host-show controller-0 | grep mgmt_ip | grep -Eo '[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}'`

cd /etc/tempest
cp -p tempest.conf tempest.conf.orig`date +%Y-%m-%d_%H%M%S`

sed -i.bkp "s|uri = http://192.168.204.2:5000/v2.0/|uri = http://${MGMT_IP}:5000/v2.0/|g" tempest.conf
sed -i.bkp "s/127.0.0.1/192.168.204.2/g" tempest.conf
sed -i.bkp "s/8081\/keystone\/main/5000/g" tempest.conf
sed -i.bkp "s/password = root/password = password/" tempest.conf
sed -i.bkp "s/admin_password = password/admin_password = ${ADMINPASS}/" tempest.conf

replace=`nova image-list |grep cirros | awk '{print $2}'| tail -n 1`
sed -i.bkp "s/{\$IMAGE_ID}/$replace/" tempest.conf

replace=`nova image-list |grep wrl5-avp | awk '{print $2}'| tail -n 1`
sed -i.bkp "s/{\$IMAGE_ID_ALT}/$replace/" tempest.conf

sed -i.bkp "s/flavor_ref_alt = 1/flavor_ref_alt = 2/" tempest.conf
sed -i.bkp "s/image_ssh_user = root/image_ssh_user = cirros/" tempest.conf
sed -i.bkp "s/image_ssh_password = password/image_ssh_password = cubwins:)/" tempest.conf
sed -i.bkp "s/image_alt_ssh_password = password/image_alt_ssh_password = root/" tempest.conf

replace=`neutron net-list |grep $PUBLIC_NETWORK| awk '{print $2}'| tail -n 1`
#replace=`neutron net-list |grep public-net0| awk '{print $2}'| tail -n 1`
#replace=`neutron net-list |grep tenant1-net1| awk '{print $2}'| tail -n 1`
sed -i.bkp "s/{\$PUBLIC_NETWORK_ID}/$replace/" tempest.conf

replace=`neutron router-list |grep $PUBLIC_ROUTER| awk '{print $2}'| tail -n 1`
#replace=`neutron router-list |grep public-router0| awk '{print $2}'| tail -n 1`
#replace=`neutron router-list |grep tenant1-router| awk '{print $2}'| tail -n 1`
sed -i.bkp "s/{\$PUBLIC_ROUTER_ID}/$replace/" tempest.conf

sed -i.bkp "s/img_dir = \/home\/root\/images\//img_dir = \/home\/wrsroot\/images\//" tempest.conf

echo "
[external_host]
external_ip = $NATIP
external_user = $NATUSER
external_passwd = $NATPASS
" >> tempest.conf

echo "
[Lab_info]
controller_0_lab = $controller0
controller_1_lab = $controller1
compute_0_lab = $compute0
compute_1_lab = $compute1
" >> tempest.conf

echo "
[host_credentials]
host_user = wrsroot
host_password = ${WRSPASS}
" >> tempest.conf


