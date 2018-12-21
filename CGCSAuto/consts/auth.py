class Tenant:
    __PASSWORD = 'Li69nux*'
    __REGION = 'RegionOne'
    __URL = 'http://192.168.204.2:5000/v3/'
    __DC_MAP = {'SystemController': {'region': 'SystemController', 'auth_url': __URL},
                'RegionOne': {'region': 'RegionOne', 'auth_url': __URL}}

    ADMIN = {
        'user': 'admin',
        'password': __PASSWORD,
        'tenant': 'admin',
        'auth_url': __URL,
        'region': __REGION
    }

    TENANT1 = {
        'user': 'tenant1',
        'password': __PASSWORD,
        'tenant': 'tenant1',
        'auth_url': __URL,
        'region': __REGION
    }

    TENANT2 = {
        'user': 'tenant2',
        'password': __PASSWORD,
        'tenant': 'tenant2',
        'auth_url': __URL,
        'region': __REGION
    }

    @classmethod
    def add_dc_region(cls, region_info):
        cls.__DC_MAP.update(region_info)

    @classmethod
    def set_url(cls, url, central_region=False):
        """
        Set default auth_url for all 3 tenant/user
        Args:
            url (str):
            central_region (bool)
        """
        if central_region:
            cls.__DC_MAP.get('SystemController')['auth_url'] = url
            cls.__DC_MAP.get('RegionOne')['auth_url'] = url
        else:
            cls.__URL = url
            cls.ADMIN['auth_url'] = url
            cls.TENANT1['auth_url'] = url
            cls.TENANT2['auth_url'] = url

    @classmethod
    def set_region(cls, region):
        """
        Set default region for all 3 tenant/user
        Args:
            region (str): e.g., SystemController, subcloud-2

        """
        cls.__REGION = region
        cls.ADMIN['region'] = region
        cls.TENANT1['region'] = region
        cls.TENANT2['region'] = region

    @classmethod
    def add(cls, tenantname, dictname=None, username=None, password=None, region=None, auth_url=None):
        tenant_dict = dict(tenant=tenantname)
        tenant_dict['user'] = username if username else tenantname
        tenant_dict['password'] = password if password else cls.__PASSWORD
        tenant_dict['region'] = region if region else cls.__REGION
        tenant_dict['auth_url'] = auth_url if auth_url else cls.__URL

        dict_name = dictname.upper() if dictname else tenantname.upper().replace('-', '_')
        setattr(cls, dict_name, tenant_dict)
        return tenant_dict

    __primary = TENANT1

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
        tenant_dictname = tenant_dictname.upper().replace('-', '_')
        tenant_dict = getattr(cls, tenant_dictname)

        if not dc_region:
            return tenant_dict

        region_dict = cls.__DC_MAP.get(dc_region, None)
        if not region_dict:
            raise ValueError('Distributed cloud region {} is not added to DC_MAP yet. DC_MAP: {}'.
                             format(dc_region, cls.__DC_MAP))

        region_dict.update({'user': tenant_dict['user'],
                            'password': tenant_dict['password'],
                            'tenant': tenant_dict['tenant']})
        return region_dict

    @classmethod
    def set_primary(cls, tenant):
        """
        should be called after _set_region and _set_url
        Args:
            tenant (dict): Tenant dict

        Returns:

        """
        cls.__primary = tenant

    @classmethod
    def get_primary(cls):
        return cls.__primary

    @classmethod
    def get_secondary(cls):
        primary = cls.get_primary()
        if primary is cls.TENANT1:
            return cls.TENANT2
        elif primary is cls.TENANT2:
            return cls.TENANT1
        else:   # primary is neither TENANT1/2
            return cls.TENANT1

    @classmethod
    def update(cls, tenant_dictname, username=None, password=None, tenant=None):
        tenant_dict = cls.get(tenant_dictname)
        if not isinstance(tenant_dict, dict):
            raise ValueError("{} dictionary does not exist in CGCSAuto/consts/auth.py".format(tenant_dictname))

        if not username and not password and not tenant:
            raise ValueError("Please specify username, password and/or tenant to change to for {} dict".
                             format(tenant_dictname))

        if username:
            tenant_dict['user'] = username
        if password:
            tenant_dict['password'] = password
        if tenant:
            tenant_dict['tenant'] = tenant

    @classmethod
    def get_dc_map(cls):
        return cls.__DC_MAP


class HostLinuxCreds:

    __WRSROOT = {
        'user': 'wrsroot',
        'password': 'Li69nux*'
    }

    @classmethod
    def get_user(cls):
        return cls.__WRSROOT['user']

    @classmethod
    def get_password(cls):
        return cls.__WRSROOT['password']

    @classmethod
    def set_user(cls, username):
        cls.__WRSROOT['user'] = username

    @classmethod
    def set_password(cls, password):
        cls.__WRSROOT['password'] = password


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
    PROMPT = '[\[]?svc-cgcsauto@.*\$[ ]?'


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

