class Tenant:
    __REGION = 'RegionOne'
    __URL = 'http://192.168.204.2:5000/v3/'

    ADMIN = {
        'user': 'admin',
        'password': 'admin',
        'tenant': 'admin',
        'auth_url': __URL,
        'region': __REGION
    }

    TENANT_1 = {
        'user': 'tenant1',
        'password': 'tenant1',
        'tenant': 'tenant1',
        'auth_url': __URL,
        'region': __REGION
    }

    TENANT_2 = {
        'user': 'tenant2',
        'password': 'tenant2',
        'tenant': 'tenant2',
        'auth_url': __URL,
        'region': __REGION
    }

    @classmethod
    def _set_url(cls, url):
        cls.ADMIN['auth_url'] = url
        cls.TENANT_1['auth_url'] = url
        cls.TENANT_2['auth_url'] = url

    @classmethod
    def _set_region(cls, region):
        cls.ADMIN['region'] = region
        cls.TENANT_1['region'] = region
        cls.TENANT_2['region'] = region

    @classmethod
    def add_tenant(cls, tenantname, dictname=None, username=None, password=None):
        tenant_dict = dict(tenant=tenantname)
        tenant_dict['user'] = username if username else tenantname
        tenant_dict['password'] = password if password else tenant_dict['user']

        dict_name = dictname.upper() if dictname else tenantname.upper()
        setattr(cls, dict_name, tenant_dict)

    __primary = TENANT_1

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


class Host:
    USER = 'wrsroot'
    PASSWORD = "Li69nux*"

    @classmethod
    def set_user(cls, username):
        cls.USER = username

    @classmethod
    def set_password(cls, password):
        cls.PASSWORD = password


class Guest:
    CREDS = {

        'cgcs-guest': {
            'user': 'root',
            'password': 'root'
        },

        'ubuntu': {
            'user': 'ubuntu',
            'password': None
        },

        'centos': {
            'user': 'centos',
            'password': None
        }
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
    HOME = '/home/svc-cgcsauto'
