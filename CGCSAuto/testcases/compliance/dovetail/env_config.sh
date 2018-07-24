[None]
# Project-level authentication scope (name or ID), recommend admin project.=
export OS_PROJECT_NAME=admin
# For identity v2, it uses OS_TENANT_NAME rather than OS_PROJECT_NAME.=
export OS_TENANT_NAME=admin
# Authentication username, belongs to the project above, recommend admin user.=
export OS_USERNAME=admin
# Authentication password. Use your own password=
export OS_PASSWORD=Li69nux*
# Authentication URL, one of the endpoints of keystone service. If this is v3 version, 
# there need some extra variables as follows.=
export OS_AUTH_URL='http://128.224.151.212:5000/v3'
# Default is 2.0. If use keystone v3 API, this should be set as 3.=
export OS_IDENTITY_API_VERSION=3
# Domain name or ID containing the user above. 
# Command to check the domain: openstack user show <OS_USERNAME>=
export OS_USER_DOMAIN_NAME=Default
# Domain name or ID containing the project aove.=
# Command to check the domain: openstack project show <OS_PROJECT_NAME>=
export OS_PROJECT_DOMAIN_NAME=Default
# Special environment parameters for https. 
# If using https + cacert, the path of cacert file should be provided. 
# The cacert file should be put at $DOVETAIL_HOME/pre_config. 
#export OS_CACERT=/home/opnfv/dovetail/pre_config/cacert.pem 

# If using https + no cacert, should add OS_INSECURE environment parameter.=
export OS_INSECURE=True
export DOVETAIL_HOME=/home/dovetail
export OS_PROJECT_ID= 5ca357bd7d7a4e02a4b596190428efe2
export OS_REGION_NAME="RegionOne"

