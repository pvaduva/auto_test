import os
from consts.filepaths import BuildServerPath, WRSROOT_HOME


class ProjVar:
    __var_dict = {'BUILD_ID': None,
                  'BUILD_SERVER': None,
                  'LOG_DIR': None,
                  'SOURCE_CREDENTIAL': None,
                  'VSWITCH_INFO_HOSTS': [],
                  'SW_VERSION': [],
                  'PATCH': None,
                  'SESSION_ID': None,
                  'CGCS_DB': True,
                  'IS_SIMPLEX': False,
                  'KEYSTONE_DEBUG': False,
                  'TEST_NAME': None,
                  'PING_FAILURE': False,
                  'COLLECT_KPI': False,
                  'LAB': None,
                  'ALWAYS_COLLECT': False,
                  'REGION': 'RegionOne',
                  }

    @classmethod
    def set_vars(cls, lab, natbox, logdir, tenant, is_boot, collect_all, report_all, report_tag, openstack_cli):

        labname = lab['short_name']

        cls.__var_dict.update(**{
            'KEYFILE_PATH': '/folk/svc-cgcsauto/priv_keys/keyfile_{}.pem'.format(labname),
            'KEYFILE_NAME': '/home/wrsroot/.ssh/' + 'keyfile_{}.pem'.format(labname),
            'LOG_DIR': logdir,
            'TCLIST_PATH': logdir + '/test_results.log',
            'PYTESTLOG_PATH': logdir + '/pytestlog.log',
            'LAB_NAME': lab['short_name'],
            'TEMP_DIR': logdir + '/tmp_files/',
            'PING_FAILURE_DIR': logdir + '/ping_failures/',
            'PRIMARY_TENANT': tenant,
            'LAB': lab,
            'BOOT_VMS': is_boot,
            'NATBOX': natbox,
            'COLLECT_ALL': collect_all,
            'REPORT_ALL': report_all,
            'REPORT_TAG': report_tag,
            'OPENSTACK_CLI': openstack_cli,
            'KPI_PATH': logdir + '/kpi.ini'
        })

    @classmethod
    def set_var(cls, append=False, **kwargs):
        for key, val in kwargs.items():
            if append:
                cls.__var_dict[key.upper()].append(val)
            else:
                cls.__var_dict[key.upper()] = val

    @classmethod
    def get_var(cls, var_name):
        var_name = var_name.upper()
        valid_vars = cls.__var_dict.keys()
        if var_name not in valid_vars:
            raise ValueError("Invalid var_name: {}. Valid vars: {}".format(var_name, valid_vars))

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
                         out_put_dir=None,
                         boot_server=None,
                         controller0_ceph_mon_device=None,
                         controller1_ceph_mon_device=None,
                         ceph_mon_gib=None):

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
            # Default tuxlab for boot
            'BOOT_SERVER':  boot_server if boot_server else 'yow-tuxlab2',

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
            'CONTROLLER0_CEPH_MON_DEVICE': controller0_ceph_mon_device,
            'CONTROLLER1_CEPH_MON_DEVICE': controller1_ceph_mon_device,
            'CEPH_MON_GIB': ceph_mon_gib
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

    __var_dict = {}
    __upgrade_steps = {}

    @classmethod
    def set_upgrade_vars(cls, build_server=None,
                         tis_build_dir=None,
                         upgrade_version=None,
                         upgrade_license_path=None,
                         patch_dir=None,
                         orchestration_after=None,
                         storage_apply_strategy=None,
                         compute_apply_strategy=None,
                         max_parallel_computes=None,
                         alarm_restrictions=None):

        __build_server = build_server if build_server else BuildServerPath.DEFAULT_BUILD_SERVER

        cls.__var_dict = {

            'UPGRADE_VERSION': upgrade_version,
            # TIS BUILD info
            'BUILD_SERVER': __build_server,
            'TIS_BUILD_DIR':
                tis_build_dir if tis_build_dir
                else (BuildServerPath.LATEST_HOST_BUILD_PATHS[upgrade_version]
                      if upgrade_version in BuildServerPath.LATEST_HOST_BUILD_PATHS
                      else BuildServerPath.DEFAULT_HOST_BUILD_PATH),

            'PATCH_DIR':
                patch_dir if patch_dir
                else (BuildServerPath.PATCH_DIR_PATHS[upgrade_version]
                      if upgrade_version in BuildServerPath.PATCH_DIR_PATHS else None),

            # Generic
            'UPGRADE_LICENSE': upgrade_license_path,
            # Orchestration -  the orchestration starting point after certain number of nodes upgraded normally
            #  eg:  controller -  indicate after controllers are upgraded the remaining are upgraded through
            #        orchestration.
            #       compute:1 - indicate orchestrations starts after one compute is upgraded.
            'ORCHESTRATION_AFTER': orchestration_after,
            'STORAGE_APPLY_TYPE': storage_apply_strategy,
            'COMPUTE_APPLY_TYPE': compute_apply_strategy,
            'MAX_PARALLEL_COMPUTES': max_parallel_computes,
            'ALARM_RESTRICTIONS': alarm_restrictions,

            # User/password to build server
            # "USERNAME": getpass.getuser(),
            # "PASSWORD": getpass.getpass(),
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


class PatchingVars:
    __var_dict = {
        'DEF_PATCH_BUILD_SERVER': BuildServerPath.DEFAULT_BUILD_SERVER,
        'DEF_PATCH_BUILD_BASE_DIR': '/localdisk/loadbuild/jenkins/CGCS_5.0_Test_Patch_Build',
        'DEF_PATCH_IN_LAB_BASE_DIR': os.path.join(WRSROOT_HOME, 'patch-files'),
        'DEF_PATCH_DIR': '/localdisk/loadbuild/jenkins/CGCS_5.0_Test_Patch_Build',
        'PATCH_DIR': None,
        'PATCH_BUILD_SERVER': BuildServerPath.DEFAULT_BUILD_SERVER,
        'USERNAME': 'svc-cgcsauto',  # getpass.getuser()
        'PASSWORD': ')OKM0okm',  # getpass.getpass()
    }

    @classmethod
    def get_patching_var(cls, var_name):
        var_name = var_name.upper()

        if var_name not in cls.__var_dict:
            raise ValueError("Invalid var_name. Valid vars: {}".format(var_name))

        return cls.__var_dict[var_name]

    @classmethod
    def set_patching_var(cls, **kwargs):
        cls.__var_dict.update(**kwargs)


class BackupRestore:
    USB_MOUNT_POINT = '/media/wrsroot'
    USB_BACKUP_PATH = '{}/backups'.format(USB_MOUNT_POINT)
    LOCAL_BACKUP_PATH = '/sandbox/backups'


class RestoreVars:

    __var_dict = {}

    @classmethod
    def set_restore_vars(cls, backup_src=None,
                         backup_src_path=None,
                         backup_build_id=None,
                         backup_builds_dir=None):

        if backup_src.lower() == 'usb':
            if backup_src_path is None or \
                    (backup_src_path is not None and BackupRestore.USB_MOUNT_POINT not in backup_src_path):
                backup_src_path = BackupRestore.USB_BACKUP_PATH

        elif backup_src.lower() == 'local':
            if backup_src_path is None:
                backup_src_path = BackupRestore.LOCAL_BACKUP_PATH

        cls.__var_dict = {
            'BACKUP_SRC': backup_src if backup_src else "USB",
            'BACKUP_SRC_PATH': backup_src_path,
            'BACKUP_BUILD_ID': backup_build_id if backup_build_id else None,

            'BACKUP_BUILDS_DIR': backup_builds_dir if backup_builds_dir
            else os.path.basename(BuildServerPath.DEFAULT_HOST_BUILDS_DIR),
            'BACKUP_SRC_SERVER': None,
        }

    @classmethod
    def get_restore_var(cls, var_name):
        var_name = var_name.upper()

        if var_name not in cls.__var_dict:
            raise ValueError("Invalid var_name. Valid vars: {}".format(var_name))

        return cls.__var_dict[var_name]

    @classmethod
    def set_restore_var(cls, **kwargs):
        for key, val in kwargs.items():
            print("Key: {} Value: {}".format(key, val))
            cls.__var_dict[key.upper()] = val


class BackupVars:

    __var_dict = {}

    @classmethod
    def set_backup_vars(cls, backup_dest=None, backup_dest_path=None, delete_backups=True, dest_labs=None):

        if backup_dest.lower() == 'usb':
            if backup_dest_path is None or \
                    (backup_dest_path is not None and BackupRestore.USB_MOUNT_POINT not in backup_dest_path):
                backup_dest_path = BackupRestore.USB_BACKUP_PATH

        elif backup_dest.lower() == 'local':
            if backup_dest_path is None:
                backup_dest_path = BackupRestore.LOCAL_BACKUP_PATH

        cls.__var_dict = {
            'BACKUP_DEST': backup_dest.lower() if backup_dest else "usb",
            'BACKUP_DEST_PATH': backup_dest_path,
            'DELETE_BUCKUPS': delete_backups,
            'DEST_LABS': dest_labs.split(',') if dest_labs else None,
            'BACKUP_DEST_SERVER': None,
        }

    @classmethod
    def get_backup_var(cls, var_name):
        var_name = var_name.upper()

        if var_name not in cls.__var_dict:
            raise ValueError("Invalid var_name. Valid vars: {}".format(var_name))

        return cls.__var_dict[var_name]

    @classmethod
    def set_backup_var(cls, **kwargs):
        for key, val in kwargs.items():
            print("Key: {} Value: {}".format(key, val))
            cls.__var_dict[key.upper()] = val
