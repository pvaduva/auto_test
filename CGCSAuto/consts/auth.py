class Tenant:
    __REGION = 'RegionOne'
    __URL = 'http://192.168.204.2:5000/v3/'

    ADMIN = {
        'user': 'admin',
        'password': 'Li69nux*',
        'tenant': 'admin',
        'auth_url': __URL,
        'region': __REGION
    }

    TENANT1 = {
        'user': 'tenant1',
        'password': 'Li69nux*',
        'tenant': 'tenant1',
        'auth_url': __URL,
        'region': __REGION
    }

    TENANT2 = {
        'user': 'tenant2',
        'password': 'Li69nux*',
        'tenant': 'tenant2',
        'auth_url': __URL,
        'region': __REGION
    }

    @classmethod
    def set_url(cls, url):
        cls.ADMIN['auth_url'] = url
        cls.TENANT1['auth_url'] = url
        cls.TENANT2['auth_url'] = url

    @classmethod
    def set_region(cls, region):
        cls.ADMIN['region'] = region
        cls.TENANT1['region'] = region
        cls.TENANT2['region'] = region

    @classmethod
    def add_tenant(cls, tenantname, dictname=None, username=None, password=None):
        tenant_dict = dict(tenant=tenantname)
        tenant_dict['user'] = username if username else tenantname
        tenant_dict['password'] = password if password else tenant_dict['user']

        dict_name = dictname.upper() if dictname else tenantname.upper()
        setattr(cls, dict_name, tenant_dict)

    __primary = TENANT1

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
    def update_tenant_dict(cls, tenant_dictname, username=None, password=None, tenant=None):
        tenant_dictname = tenant_dictname.upper()
        tenant_dict = getattr(cls, tenant_dictname)
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

        setattr(cls, tenant_dictname, tenant_dict)


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
    HOSTNAME = 'yow-cgcs-test.wrs.com'
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
