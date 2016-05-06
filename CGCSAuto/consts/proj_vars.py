class ProjVar:
    __var_dict = {}
    # __var_dict = {
    #     'KEYFILE_PATH': None,
    #     'KEYFILE_NAME': None,
    #     'LOG_DIR': None,
    #     'TCLIST_PATH': None,
    #     'PYTESTLOG_PATH': None,
    #     'LAB_NAME': None,
    #     'TEMP_DIR': None,
    #     'PRIMARY_TENANT': None,
    #     'LAB': None,
    #     'BOOT_VMS': None,
    #     'NATBOX': None
    # }

    @classmethod
    def set_vars(cls, lab, natbox, logdir, tenant, is_boot):
        labname = lab['short_name']

        cls.__var_dict = {
            'KEYFILE_PATH': 'keyfile_{}.pem'.format(labname),
            'KEYFILE_NAME': '/home/wrsroot/.ssh/' + 'keyfile_{}.pem'.format(labname),
            'LOG_DIR': logdir,
            'TCLIST_PATH': logdir + '/testcases.lst',
            'PYTESTLOG_PATH': logdir + '/pytestlog.log',
            'LAB_NAME': lab['short_name'],
            'TEMP_DIR': logdir + '/tmp_files',
            'PRIMARY_TENANT': tenant,
            'LAB': lab,
            'BOOT_VMS': is_boot,
            'NATBOX': natbox,
        }

    @classmethod
    def get_var(cls, var_name):
        valid_vars = cls.__var_dict.keys()
        if var_name not in valid_vars:
            raise ValueError("Invalid var_name. Valid vars: {}".format(valid_vars))

        return cls.__var_dict[var_name]
