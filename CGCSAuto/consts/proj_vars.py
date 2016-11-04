class ProjVar:
    __var_dict = {}

    @classmethod
    def set_vars(cls, lab, natbox, logdir, tenant, is_boot, collect_all, report_all, report_tag, openstack_cli):

        labname = lab['short_name']

        cls.__var_dict = {
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
            'OPENSTACK_CLI': openstack_cli
        }

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
    DEFAULT_BUILD_SERVER = 'yow-cgts4-lx'
    __var_dict = {
        'TIS_BUILD_DIR': '/localdisk/loadbuild/jenkins/TS_16.10_Host/',

    }
    __install_steps = {}

    @classmethod
    def set_install_vars(cls, lab, resume, host_build_dir, controllers, computes, storages, hosts_bulk_add,
                         boot_if_settings, license_path, tis_config, skip_labsetup, lab_setup, guest_image,
                         heat_templates, build_server=DEFAULT_BUILD_SERVER):

        cls.__var_dict = {
            'LAB': lab,
            'LAB_NAME': lab['short_name'],
            'RESUME': resume,

            # TIS BUILD info
            'BUILD_SERVER': build_server,
            'TIS_BUILD_DIR': host_build_dir,
            'LAB_CONF_DIR': "{}/rt/repo/addons/wr-cgcs/layers/cgcs/extras.ND/lab/yow/{}".format(host_build_dir,
                                                                                                lab['name']),
            # Nodes info
            'CONTROLLERS_CODES': controllers,
            'COMPUTES_CODES': computes,
            'STORAGES': storages,
            'BOOT_IF_SETTINGS': boot_if_settings,
            'HOSTS_BULK_ADD': hosts_bulk_add,

            # Config controller info
            'TIS_CONFIG': tis_config,
            'LICENSE': license_path,

            # Lab setup and test files
            'SKIP_LABSETUP': skip_labsetup,
            'LAB_SETUP_PATH': lab_setup,
            'GUEST_IMAGE': guest_image,
            'HEAT_TEMPLATES': heat_templates,

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
