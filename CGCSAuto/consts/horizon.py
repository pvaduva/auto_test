from consts.proj_vars import ProjVar

ADMIN_USERNAME = 'admin'
ADMIN_PASSWORD = 'Li69nux*'
TENANT_USERNAME = 'tenant1'
TENANT_PASSWORD = 'Li69nux*'
HORIZON_URL = 'http://' + ProjVar.get_var("LAB")['floating ip']
TEMP_DIR = ProjVar.get_var('TEMP_DIR')
# IS_HORIZON_VISIBLE = ProjVar.get_var('HORIZON_VISIBLE')
DEFAULT_SUBNET = 'external-net0'
