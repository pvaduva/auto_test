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
