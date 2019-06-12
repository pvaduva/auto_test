class Tenant:
    __PASSWORD = 'Li69nux*'
    __REGION = 'RegionOne'
    __URL_PLATFORM = 'http://192.168.204.2:5000/v3/'
    __URL_CONTAINERS = 'http://keystone.openstack.svc.cluster.local/v3'
    __DC_MAP = {'SystemController': {'region': 'SystemController', 'auth_url': __URL_PLATFORM},
                'RegionOne': {'region': 'RegionOne', 'auth_url': __URL_PLATFORM}}

    # Platform openstack user - admin
    ADMIN_PLATFORM = {
        'user': 'admin',
        'password': __PASSWORD,
        'tenant': 'admin',
        'domain': 'Default',
        'platform': True,
    }

    # Containerized openstack users - admin, and two test users/tenants
    ADMIN = {
        'user': 'admin',
        'password': __PASSWORD,
        'tenant': 'admin',
        'domain': 'Default'
    }

    TENANT1 = {
        'user': 'tenant1',
        'password': __PASSWORD,
        'tenant': 'tenant1',
        'domain': 'Default',
        'nova_keypair': 'keypair-tenant1'
    }

    TENANT2 = {
        'user': 'tenant2',
        'password': __PASSWORD,
        'tenant': 'tenant2',
        'domain': 'Default',
        'nova_keypair': 'keypair-tenant2'
    }

    @classmethod
    def add_dc_region(cls, region_info):
        cls.__DC_MAP.update(region_info)

    @classmethod
    def set_platform_url(cls, url, central_region=False):
        """
        Set auth_url for platform keystone
        Args:
            url (str):
            central_region (bool)
        """
        if central_region:
            cls.__DC_MAP.get('SystemController')['auth_url'] = url
            cls.__DC_MAP.get('RegionOne')['auth_url'] = url
        else:
            cls.__URL_PLATFORM = url

    @classmethod
    def set_region(cls, region):
        """
        Set default region for all tenants
        Args:
            region (str): e.g., SystemController, subcloud-2

        """
        cls.__REGION = region

    @classmethod
    def add(cls, tenantname, dictname=None, username=None, password=None, region=None, auth_url=None, domain='Default'):
        tenant_dict = dict(tenant=tenantname)
        tenant_dict['user'] = username if username else tenantname
        tenant_dict['password'] = password if password else cls.__PASSWORD
        tenant_dict['domain'] = domain
        if region:
            tenant_dict['region'] = region
        if auth_url:
            tenant_dict['auth_url'] = auth_url

        dict_name = dictname.upper() if dictname else tenantname.upper().replace('-', '_')
        setattr(cls, dict_name, tenant_dict)
        return tenant_dict

    __primary = 'TENANT1'

    @classmethod
    def get(cls, tenant_dictname, dc_region=None):
        """
        Get tenant auth dict that can be passed to auth_info in cli cmd
        Args:
            tenant_dictname (str): e.g., tenant1, TENANT2, system_controller
            dc_region (None|str): key for dc_region added via add_dc_region. Used to update auth_url and region
                e.g., SystemController, RegionOne, subcloud-2

        Returns (dict): mutable dictionary. If changed, DC map or tenant dict will update as well.

        """
        import copy
        tenant_dictname = tenant_dictname.upper().replace('-', '_')
        tenant_dict = getattr(cls, tenant_dictname)
        tenant_dict = copy.deepcopy(tenant_dict)

        if dc_region:
            region_dict = cls.__DC_MAP.get(dc_region, None)
            if not region_dict:
                raise ValueError('Distributed cloud region {} is not added to DC_MAP yet. DC_MAP: {}'.
                                 format(dc_region, cls.__DC_MAP))
            tenant_dict.update({'region': region_dict['region']})

        return tenant_dict

    @classmethod
    def get_region_and_url(cls, platform=False, dc_region=None):
        auth_region_and_url = {
            'auth_url': cls.__URL_PLATFORM if platform else cls.__URL_CONTAINERS,
            'region': cls.__REGION
        }

        if dc_region:
            region_dict = cls.__DC_MAP.get(dc_region, None)
            if not region_dict:
                raise ValueError('Distributed cloud region {} is not added to DC_MAP yet. DC_MAP: {}'.
                                 format(dc_region, cls.__DC_MAP))
            auth_region_and_url['region'] = region_dict.get('region')
            if platform:
                auth_region_and_url['auth_url'] = region_dict.get('auth_url')

        return auth_region_and_url

    @classmethod
    def set_primary(cls, tenant):
        """
        should be called after _set_region and _set_url
        Args:
            tenant (str): Tenant dict name

        Returns:

        """
        cls.__primary = tenant.upper()

    @classmethod
    def get_primary(cls):
        return cls.get(tenant_dictname=cls.__primary)

    @classmethod
    def get_secondary(cls):
        secondary = 'TENANT1' if cls.__primary != 'TENANT1' else 'TENANT2'
        return cls.get(tenant_dictname=secondary)

    @classmethod
    def update(cls, tenant_dictname, username=None, password=None, tenant=None, domain=None):
        tenant_dictname = tenant_dictname.upper().replace('-', '_')
        tenant_dict = getattr(cls, tenant_dictname)

        if not isinstance(tenant_dict, dict):
            raise ValueError("{} dictionary does not exist in CGCSAuto/consts/auth.py".format(tenant_dictname))

        if not username and not password and not tenant and not domain:
            raise ValueError("Please specify username, password, tenant, and/or domain to update for {} dict".
                             format(tenant_dictname))

        if username:
            tenant_dict['user'] = username
        if password:
            tenant_dict['password'] = password
        if tenant:
            tenant_dict['tenant'] = tenant
        if domain:
            tenant_dict['domain'] = domain

    @classmethod
    def get_dc_map(cls):
        return cls.__DC_MAP


class HostLinuxCreds:

    __SYSADMIN = {
        'user': 'sysadmin',
        'password': 'Li69nux*'
    }

    @classmethod
    def get_user(cls):
        return cls.__SYSADMIN['user']

    @classmethod
    def get_password(cls):
        return cls.__SYSADMIN['password']

    @classmethod
    def set_user(cls, username):
        cls.__SYSADMIN['user'] = username

    @classmethod
    def set_password(cls, password):
        cls.__SYSADMIN['password'] = password


class Guest:
    CREDS = {
        'tis-centos-guest': {
            'user': 'root',
            'password': 'root'
        },

        'cgcs-guest': {
            'user': 'root',
            'password': 'root'
        },

        'ubuntu': {
            'user': 'ubuntu',
            'password': None
        },

        'centos_6': {
            'user': 'centos',
            'password': None
        },

        'centos_7': {
            'user': 'centos',
            'password': None
        },

        # This image has some issue where it usually fails to boot
        'opensuse_13': {
            'user': 'root',
            'password': None
        },

        # OPV image has root/root enabled
        'rhel': {
            'user': 'root',
            'password': 'root'
        },

        'cirros': {
            'user': 'cirros',
            'password': 'cubswin:)'
        },

        'win_2012': {
            'user': 'Administrator',
            'password': 'Li69nux*'
        },

        'win_2016': {
            'user': 'Administrator',
            'password': 'Li69nux*'
        },

        'ge_edge': {
            'user': 'root',
            'password': 'root'
        },

        'vxworks': {
            'user': 'root',
            'password': 'root'
        },

    }

    @classmethod
    def set_user(cls, image_name, username):
        cls.CREDS[image_name]['user'] = username

    @classmethod
    def set_password(cls, image_name, password):
        cls.CREDS[image_name]['password'] = password


class SvcCgcsAuto:
    SERVER = '128.224.150.21'
    USER = 'svc-cgcsauto'
    PASSWORD = ')OKM0okm'
    VLM_PASSWORD = 'wrssvc-cgcsauto'
    HOME = '/home/svc-cgcsauto'
    SANDBOX = '/sandbox'
    HOSTNAME = 'yow-cgcs-test'
    PROMPT = r'[\[]?svc-cgcsauto@.*\$[ ]?'


class CliAuth:

    __var_dict = {
        'OS_AUTH_URL': 'http://192.168.204.2:5000/v3',
        'OS_ENDPOINT_TYPE': 'internalURL',
        'CINDER_ENDPOINT_TYPE': 'internalURL',
        'OS_USER_DOMAIN_NAME': 'Default',
        'OS_PROJECT_DOMAIN_NAME': 'Default',
        'OS_IDENTITY_API_VERSION': '3',
        'OS_REGION_NAME': 'RegionOne',
        'OS_INTERFACE': 'internal',
        'HTTPS': False,
        'OS_KEYSTONE_REGION_NAME': None,
        }

    @classmethod
    def set_vars(cls, **kwargs):

        for key in kwargs:
            cls.__var_dict[key.upper()] = kwargs[key]

    @classmethod
    def get_var(cls, var_name):
        var_name = var_name.upper()
        valid_vars = cls.__var_dict.keys()
        if var_name not in valid_vars:
            raise ValueError("Invalid var_name. Valid vars: {}".format(valid_vars))

        return cls.__var_dict[var_name]


class ComplianceCreds:
    __HOST = {
        'host': 'tis-compliance-test-node.cumulus.wrs.com',
        'user': 'cumulus',
        'password': 'kumuluz'
    }

    @classmethod
    def get_user(cls):
        return cls.__HOST['user']

    @classmethod
    def get_password(cls):
        return cls.__HOST['password']

    @classmethod
    def get_host(cls):
        return cls.__HOST['host']

    @classmethod
    def set_user(cls, username):
        cls.__HOST['user'] = username

    @classmethod
    def set_password(cls, password):
        cls.__HOST['password'] = password

    @classmethod
    def set_host(cls, host):
        cls.__HOST['host'] = host


class CumulusCreds:
    HOST = '128.224.151.50'
    LINUX_USER = 'svc-cgcsauto'
    LINUX_PASSWORD = ')OKM0okm'
    AUTH_URL = 'http://{}:5000/v3'.format(HOST)

    TENANT_TIS_LAB = {
        'user': 'svc-cgcsauto',
        'password': 'svc-cgcsauto',
        'tenant': 'tis-lab',
        'auth_url': AUTH_URL,
        'region': 'RegionOne'
    }
