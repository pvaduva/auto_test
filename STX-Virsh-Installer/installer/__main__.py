import os
import datetime
import configparser

import installer
from installer import template, libvirt
from installer.helper import installer_log, setup, deployment, parser


def validate_var_dict(var_dict):
    """Validates the variable dictionary, terminates the installer if necessary

    :param var_dict: A dictionary contains all the variables
    :return:
    """
    if not os.path.exists(var_dict['base_log_dir']):
        os.makedirs(var_dict['base_log_dir'])
    if not os.path.exists(os.path.join(var_dict['base_log_dir'], var_dict['time_stamp'])):
        os.makedirs(os.path.join(var_dict['base_log_dir'], var_dict['time_stamp']))

    installer_log.log_start(os.path.join(stx_dict['base_log_dir'], stx_dict['time_stamp'],
                                         'stx_virsh_installer.log'))

    if var_dict['system_mode'] == 'standard':
        var_dict['system_mode'] = 'controllerstorage'
    if var_dict['system_mode'] == 'storage':
        var_dict['system_mode'] = 'dedicatedstorage'

    supported_mode = ['simplex', 'duplex', 'controllerstorage', 'dedicatedstorage']

    if var_dict['system_mode'] not in supported_mode:
        installer_log.log_error_msg('system mode: {} is not supported by stx_virsh_installer'
                                    .format(var_dict['system_mode']))
        exit(-1)

    if var_dict['vm_name_prefix']:
        var_dict['vm_name_prefix'] = var_dict['vm_name_prefix'] + '-'

    # hard code values based on system constraints
    if var_dict['system_mode'] == 'simplex':
        var_dict['num_of_controller'] = '1'
    if 'plex' in var_dict['system_mode']:
        var_dict['num_of_compute'] = '0'
        var_dict['num_of_storage'] = '0'
    if var_dict['system_mode'] == 'controllerstorage':
        var_dict['num_of_storage'] = '0'


if __name__ == "__main__":

    parser = parser.add_parser()
    args = parser.parse_args()
    default_template_dir = os.path.dirname(os.path.abspath(template.__file__))
    stx_dict = {'system_mode': args.mode, 'delete': args.delete,
                'template_dir': default_template_dir, 'skipvm': args.skipvm,
                'libvirt_scirpt_dir': os.path.dirname(os.path.abspath(libvirt.__file__))}

    # Allow the user to change variable values by:
    # - modifying the variable.ini .
    #   Customized files provided using this option will not be modified by the installer.
    # - providing an overwrite file that contains all the variables to change and their value in
    #   variable_name=value format for each line.
    #   Customized files provided using this option will not be modified by the installer.
    # - for providing customized files only, providing an directory that contains all the
    #   customized files. The customized files should be named exact the same as the template files
    #   to be replaced.
    #   Customized files provided using this option will not be modified by the installer.
    # - for providing customized template files only. providing an directory that contains all the
    #   customized template files.The customized template files should be named exact the same as
    #   the template files to be replaced.
    #   Customized template files provided using this option
    #   WILL be modified by the installer if needed.
    config = configparser.ConfigParser()
    config.read(os.path.join(os.path.dirname(installer.__file__), 'variable.ini'))
    stx_dict.update(config['VARIABLE'])
    
    for key in config['FILE']:
        if config['FILE'][key] == '':
            config['FILE'][key] = os.path.join(default_template_dir, key)
        else:
            config['FILE'][key] = os.path.realpath(os.path.expanduser(config['FILE'][key]))
    stx_dict.update(config['FILE'])
    stx_dict.update(config['URL'])

    if config['LOG_LOCATION']['base_log_dir'] == '':
        stx_dict['base_log_dir'] = os.path.realpath(os.path.expanduser('~/stx_virsh_installer/'))
    else:
        stx_dict['base_log_dir'] = os.path.realpath(os.path.expanduser(
            config['LOG_LOCATION']['base_log_dir']))
    stx_dict['time_stamp'] = '{0:%Y-%m-%d_%H:%M:%S}'.format(datetime.datetime.now())

    if args.overwrite is not None:
        args.customize = os.path.realpath(os.path.expanduser(args.overwrite))
        if os.path.isfile(args.overwrite):
            with open(args.overwrite, 'r') as fp:
                for line in fp:
                    if '=' in line:
                        line = line.strip()
                        contents = line.split('=')
                        stx_dict[contents[0]] = contents[1]  # expecting only one '=' in a line
    if args.customize is not None:
        args.customize = os.path.realpath(os.path.expanduser(args.customize))
        if os.path.isdir(args.customize):
            overwrite_files_list = os.listdir(args.customize)
            for a_file in overwrite_files_list:
                if a_file in stx_dict:
                    stx_dict[a_file] = os.path.join(args.customize, a_file)
    if args.template is not None:
        args.template = os.path.realpath(os.path.expanduser(args.template))
        stx_dict['replaced_template_dir'] = args.template
        if os.path.isdir(args.template):
            overwrite_template_list = os.listdir(args.template)
            for a_file in overwrite_template_list:
                if a_file in stx_dict:
                    stx_dict[a_file] = os.path.join(args.template, a_file)
    else:
        # for later checking if the installer should dynamically generate the file
        stx_dict['replaced_template_dir'] = stx_dict['template_dir']
    for fname, source_path in stx_dict.items():
        if '.' not in fname:
            continue
        stx_dict[fname] = os.path.realpath(os.path.expanduser(source_path))
    if not stx_dict['admin_password']:
        stx_dict['admin_password'] = 'St8rlingX*'

    validate_var_dict(stx_dict)

    installer_log.log_step(1, True)
    installer_log.log_var_dict(stx_dict)

    if stx_dict['delete']:
        print('about to delete {} system with name prefix {}'.format(stx_dict['system_mode'],
                                                                     stx_dict['vm_name_prefix']))
        confirmation = input('press (y/Y) to proceed deletion.'
                             ' any other input will abort deleting\n')
        if confirmation.lower() == 'y':
            setup.cleanup(stx_dict)
            installer_log.log_deleting(True)
        else:
            installer_log.log_deleting(False)
        exit(0)

    installer_log.log_step(2, False)
    nodes_list = setup.setup(stx_dict)

    # deleting bootimage.iso from dictionary since it will not be used after setup()
    del stx_dict['bootimage.iso']
    if not nodes_list:
        installer_log.log_info_msg('something went wrong when setting up environment')
    else:
        installer_log.log_step(2, True)
        if not deployment.deploy_system(nodes_list, stx_dict):
            installer_log.log_info_msg("Installation didn't finish. "
                                       "Please check logs for debugging")





