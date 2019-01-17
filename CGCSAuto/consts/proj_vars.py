from consts.filepaths import WRSROOT_HOME


class ProjVar:
    __var_dict = {'BUILD_ID': None,
                  'BUILD_SERVER': None,
                  'JOB': None,
                  'BUILD_BY': None,
                  'BUILD_PATH': None,
                  'LOG_DIR': None,
                  'SOURCE_CREDENTIAL': None,
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
                  'COLLECT_TELNET': False,
                  'TELNET_THREADS': None,
                  'SYS_TYPE': None,
                  'COLLECT_SYS_NET_INFO': False,
                  'IS_VBOX': False,
                  'RELEASE': 'R6',
                  'REMOTE_CLI': False,
                  'USER_FILE_DIR': WRSROOT_HOME,
                  'NO_TEARDOWN': False,
                  'VSWITCH_TYPE': None,
                  'IS_DC': False,
                  'PRIMARY_SUBCLOUD': None,
                  'BUILD_INFO': None,
                  'TEMP_DIR': '',  
                  }

    @classmethod
    def set_vars(cls, lab, natbox, logdir, tenant, is_boot, collect_all, report_all, report_tag, openstack_cli,
                 always_collect, horizon_visible):

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
            'GUEST_LOGS_DIR': logdir + '/guest_logs/',
            'PRIMARY_TENANT': tenant,
            'LAB': lab,
            'BOOT_VMS': is_boot,
            'NATBOX': natbox,
            'COLLECT_ALL': collect_all,
            'ALWAYS_COLLECT': always_collect,
            'REPORT_ALL': report_all,
            'REPORT_TAG': report_tag,
            'OPENSTACK_CLI': openstack_cli,
            'KPI_PATH': logdir + '/kpi.ini',
            'HORIZON_VISIBLE': horizon_visible
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
    def set_install_vars(cls, lab,
                         build_server,
                         host_build_dir,
                         guest_image,
                         guest_server,
                         files_server,
                         hosts_bulk_add,
                         boot_if_settings,
                         tis_config,
                         lab_setup,
                         heat_templates,
                         license_path,
                         boot_server,
                         iso_path,
                         iso_server,
                         controller0_ceph_mon_device,
                         controller1_ceph_mon_device,
                         boot_type='feed',
                         ceph_mon_gib=None,
                         low_latency=False,
                         security="standard",
                         stop=None,
                         patch_server=None,
                         patch_dir=None,
                         multi_region=False,
                         dist_cloud=False,
                         ovs=False,
                         kubernetes=False,
                         resume=False,
                         wipedisk=False,
                         skips=None,
                         dc_float_ip=None,
                         install_subcloud=None,
                         openstack_install=False,):

        cls.__var_dict = {
            'LAB': lab,
            'LAB_NAME': lab['short_name'],
            'RESUME': resume,
            'STOP': stop,
            'SKIP': skips if skips is not None else [],
            'WIPEDISK': wipedisk,
            'MULTI_REGION': multi_region,
            'DISTRIBUTED_CLOUD': dist_cloud,
            'OVS': ovs,
            "KUBERNETES": kubernetes,
            "OPENSTACK_INSTALL": openstack_install,
            # TIS BUILD info
            'BUILD_SERVER': build_server,
            'TIS_BUILD_DIR': host_build_dir,

            # Files paths
            'FILES_SERVER': files_server,
            'ISO_PATH': iso_path,
            'ISO_HOST': iso_server,
            'PATCH_DIR': patch_dir,
            'PATCH_SERVER': patch_server,
            # Default tuxlab for boot
            'BOOT_SERVER':  boot_server,
            'BOOT_TYPE': boot_type,
            'LOW_LATENCY': low_latency,
            'DC_FLOAT_IP': dc_float_ip,
            'INSTALL_SUBCLOUD': install_subcloud,
            'SECURITY': security,
            # Default path is <DEFAULT_LAB_FILES_DIR>/TiS_config.ini_centos|hosts_bulk_add.xml|lab_setup.conf if
            # Unspecified. This needs to be parsed/converted when rsync/scp files.
            # Lab specific
            'TIS_CONFIG': tis_config,
            'HOSTS_BULK_ADD': hosts_bulk_add,
            'BOOT_IF_SETTINGS': boot_if_settings,
            'LAB_SETUP_PATH': lab_setup,

            # Generic
            'LICENSE': license_path,
            'GUEST_IMAGE': guest_image,
            'GUEST_SERVER': guest_server,
            'HEAT_TEMPLATES': heat_templates,
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
    def set_upgrade_vars(cls, build_server,
                         tis_build_dir,
                         upgrade_version,
                         patch_dir,
                         upgrade_license_path,
                         orchestration_after=None,
                         storage_apply_strategy=None,
                         compute_apply_strategy=None,
                         max_parallel_computes=None,
                         alarm_restrictions=None):

        cls.__var_dict = {
            'UPGRADE_VERSION': upgrade_version,
            # TIS BUILD info
            'BUILD_SERVER': build_server,
            'TIS_BUILD_DIR': tis_build_dir,
            'PATCH_DIR': patch_dir,
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
        # Common patch vars
        'PATCH_DIR': None,
        'PATCH_BUILD_SERVER': None,

        # Formal release patch vars
        'PATCH_BASE_DIR': '/localdisk/loadbuild/jenkins/TC_18.03_Patch_Formal_Build',
        'CONTROLLER_APPLY_TYPE': "serial",
        'STORAGE_APPLY_TYPE': "serial",
        'COMPUTE_APPLY_TYPE': "serial",
        'MAX_PARALLEL_COMPUTES': 2,
        'INSTANCE_ACTION': "stop-start",
        'ALARM_RESTRICTIONS': "strict",
    }

    @classmethod
    def get_patching_var(cls, var_name):
        var_name = var_name.upper()

        if var_name not in cls.__var_dict:
            def_var_name = 'DEF_{}'.format(var_name)
            if def_var_name not in cls.__var_dict:
                raise ValueError("Invalid var_name. Valid vars: {}".format(var_name))
            else:
                var_name = def_var_name
        return cls.__var_dict[var_name]

    @classmethod
    def set_patching_var(cls, *, patch_dir=None, **kwargs):
        cls.__var_dict.update(patch_dir=patch_dir)
        kwargs = {k.upper(): v for k, v in kwargs.items()}
        cls.__var_dict.update(**kwargs)


class RestoreVars:

    __var_dict = {}

    @classmethod
    def set_restore_vars(cls, *, backup_src='local', **kwargs):
        kwargs = kwargs if kwargs else {}
        cls.__var_dict = {
            'BACKUP_SRC': backup_src,
            'BACKUP_SRC_PATH': kwargs.pop('backup_src_path', ''),
            'BACKUP_BUILD_ID': kwargs.pop('backup_build_id', None),
            'BACKUP_BUILDS_DIR': kwargs.pop('backup_builds_dir', None),
            'BACKUP_SRC_SERVER': kwargs.pop('backup_src_server', None),
            'SKIP_SETUP_FEED': kwargs.pop('skip_setup_feed', False),
            'SKIP_REINSTALL': kwargs.pop('skip_reinstall', False),
            'LOW_LATENCY': kwargs.pop('low_latency', False),
            'BUILD_SERVER': kwargs.pop('build_server', ''),
            'CINDER_BACKUP': kwargs.pop('cinder_backup', True),
            'REINSTALL_STORAGE': kwargs.pop('reinstall_storage', False),
        }

    @classmethod
    def get_restore_vars(cls):
        return dict(cls.__var_dict)

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
    def set_backup_vars(cls, backup_dest=None, *, **kwargs):
        kwargs = kwargs if kwargs else {}
        cls.__var_dict = {
            'BACKUP_DEST': backup_dest,
            'BACKUP_DEST_PATH': kwargs.pop('backup_dest_path', ''),
            'DELETE_BUCKUPS': kwargs.pop('delete_backups', True),
            'DEST_LABS': kwargs.pop('dest_labs', '').split() if kwargs.get('dest_labs', '') else '',
            'BACKUP_DEST_SERVER': kwargs.pop('backup_dest_server', None),
            'CINDER_BACKUP': kwargs.pop('cinder_backup', True),
            'REINSTALL_STORAGE': kwargs.pop('reinstall_storage', False),
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


class ComplianceVar:
    __var_dict = {
        'REFSTACK_SUITE': None,
        'DOVETAIL_SUITE': None,
    }

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
