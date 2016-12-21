import getpass
import os
from consts.filepaths import BuildServerPath


class ProjVar:
    # BUILD_ID,
    __var_dict = {'BUILD_ID': None,
                  'LOG_DIR': None}
                  # 'LOG_DIR': os.path.expanduser("~") + '/AUTOMATION_LOGS/Unknown'}

    @classmethod
    def set_vars(cls, lab, natbox, logdir, tenant, is_boot, collect_all, report_all, report_tag, openstack_cli):

        labname = lab['short_name']

        cls.__var_dict.update(**{
            'KEYFILE_PATH': '/home/cgcs/priv_keys/keyfile_{}.pem'.format(labname),
            'KEYFILE_NAME': '/home/wrsroot/.ssh/' + 'keyfile_{}.pem'.format(labname),
            'LOG_DIR': logdir,
            'TCLIST_PATH': logdir + '/test_results.log',
            'PYTESTLOG_PATH': logdir + '/pytestlog.log',
            'LAB_NAME': lab['short_name'],
            'TEMP_DIR': logdir + '/tmp_files/',
            'PRIMARY_TENANT': tenant,
            'LAB': lab,
            'BOOT_VMS': is_boot,
            'NATBOX': natbox,
            'COLLECT_ALL': collect_all,
            'REPORT_ALL': report_all,
            'REPORT_TAG': report_tag,
            'OPENSTACK_CLI': openstack_cli,
            'SOURCE_ADMIN': False
        })

    @classmethod
    def set_var(cls, **kwargs):
        for key, val in kwargs.items():
            cls.__var_dict[key.upper()] = val

    @classmethod
    def get_var(cls, var_name):
        var_name = var_name.upper()
        valid_vars = cls.__var_dict.keys()
        if var_name not in valid_vars:
            raise ValueError("Invalid var_name. Valid vars: {}".format(valid_vars))

        return cls.__var_dict[var_name]


class InstallVars:

    __var_dict = {}
    __install_steps = {}

    @classmethod
    def set_install_vars(cls, lab, resume, skip_labsetup,
                         build_server=None,
                         host_build_dir=None,
                         guest_image=None,
                         files_server=None,
                         hosts_bulk_add=None,
                         boot_if_settings=None,
                         tis_config=None,
                         lab_setup=None,
                         heat_templates=None,
                         license_path=None,
                         out_put_dir=None):


        __build_server = build_server if build_server else BuildServerPath.DEFAULT_BUILD_SERVER

        cls.__var_dict = {
            'LAB': lab,
            'LAB_NAME': lab['short_name'],
            'RESUME': resume,
            'SKIP_LABSETUP': skip_labsetup,

            # TIS BUILD info
            'BUILD_SERVER': __build_server,
            'TIS_BUILD_DIR': host_build_dir if host_build_dir else BuildServerPath.DEFAULT_HOST_BUILD_PATH,

            # Files paths
            'FILES_SERVER': files_server if files_server else __build_server,
            'DEFAULT_LAB_FILES_DIR': "{}/rt/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/{}".format(
                    host_build_dir, lab['name']),

            # Default path is <DEFAULT_LAB_FILES_DIR>/TiS_config.ini_centos|hosts_bulk_add.xml|lab_setup.conf if
            # Unspecified. This needs to be parsed/converted when rsync/scp files.
            # Lab specific
            'TIS_CONFIG': tis_config,
            'HOSTS_BULK_ADD': hosts_bulk_add,
            'BOOT_IF_SETTINGS': boot_if_settings,
            'LAB_SETUP_PATH': lab_setup,

            # Generic
            'LICENSE': license_path if license_path else BuildServerPath.DEFAULT_LICENSE_PATH,
            'GUEST_IMAGE': guest_image if guest_image else BuildServerPath.DEFAULT_GUEST_IMAGE_PATH,
            'HEAT_TEMPLATES': heat_templates if heat_templates else BuildServerPath.HEAT_TEMPLATES,
            'OUT_PUT_DIR': out_put_dir,
            'BUILD_ID': None,
        }

    @classmethod
    def set_install_status(cls, **steps):
        for key, value in steps.items():
            cls.__install_steps[key.upper()] = value

    @classmethod
    def get_install_status(cls, step=None):
        if step is None:
            return cls.__install_steps

        return cls.__install_steps[step]

    @classmethod
    def set_install_var(cls, **kwargs):
        for key, val in kwargs.items():
            cls.__var_dict[key.upper()] = val

    @classmethod
    def get_install_var(cls, var_name):
        var_name = var_name.upper()
        valid_vars = cls.__var_dict.keys()
        if var_name not in valid_vars:
            raise ValueError("Invalid var_name. Valid vars: {}".format(valid_vars))

        return cls.__var_dict[var_name]


    @classmethod
    def get_install_vars(cls):
        return cls.__var_dict


class UpgradeVars:

    _var_dict = {}
    __upgrade_steps = {}

    @classmethod
    def set_upgrade_vars(cls, build_server=None,
                         tis_build_dir=None,
                         upgrade_version=None,
                         upgrade_license_path=None):

        __build_server = build_server if build_server else BuildServerPath.DEFAULT_BUILD_SERVER

        cls.__var_dict = {

            'UPGRADE_VERSION': upgrade_version,
            # TIS BUILD info
            'BUILD_SERVER': __build_server,
            'TIS_BUILD_DIR': tis_build_dir if tis_build_dir else
                BuildServerPath.LATEST_HOST_BUILD_PATHS[upgrade_version],

            # Generic
            'UPGRADE_LICENSE': upgrade_license_path,

            #User/password to build server
            #"USERNAME": getpass.getuser(),
            #"PASSWORD": getpass.getpass(),
        }

    @classmethod
    def set_upgrade_status(cls, **steps):
        for key, value in steps.items():
            cls.__upgrade_steps[key.upper()] = value

    @classmethod
    def get_upgrade_status(cls, step=None):
        if step is None:
            return cls.__upgrade_steps

        return cls.__upgrade_steps[step]

    @classmethod
    def set_upgrade_var(cls, **kwargs):
        for key, val in kwargs.items():
            print("Key: {} Value: {}".format(key, val))
            cls.__var_dict[key.upper()] = val

    @classmethod
    def get_upgrade_var(cls, var_name):
        var_name = var_name.upper()
        valid_vars = cls.__var_dict.keys()
        if var_name not in valid_vars:
            raise ValueError("Invalid var_name. Valid vars: {}".format(valid_vars))

        return cls.__var_dict[var_name]


    @classmethod
    def get_upgrade_vars(cls):
        return cls.__var_dict