import logging
import datetime


step_start_deco = '{}\n{}'.format('='*20, '-'*20)
step_end_deco = '{}\n{}'.format('-'*20, '='*20)
step_dict = {1: 'Populating variable dictionary', 2: 'Set up environment',
             3: 'Booting controller-0', 4: 'Setting up environment before running ansible playbook',
             5: 'Running ansible playbook',
             6: 'Unlocking controller-0', 7: 'Wait till all nodes available',
             'lab_setup.sh': 'Running lab_setup.sh', 'bring up service': 'Bringing up services'}
logger = logging.getLogger(__name__)


def log_start(file_name, filemode='w', level=logging.DEBUG):
    logging.basicConfig(filename=file_name, filemode=filemode, level=level,
                        format='%(asctime)s stx-virsh-installer %(levelname)s: %(message)s')
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s stx-virsh-installer %(levelname)s: %(message)s')

    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.info('StarlingX Auto-installer started'.format(datetime.datetime.now()))


def log_step(step, finished):
    """
    Picks up steps from step_dict and log the status of the step

    :param step: An integer or string that corresponds to one of the key in step_dict
    :param finished: A boolean value that indicates if the step is finished or not
    :return:
    """
    if not finished:
        logger.info('\n{}\nStep {}: {} started'.format(step_start_deco, step, step_dict[step]))
    else:
        logger.info('Step {}: {} finished\n{}'.format(step, step_dict[step], step_end_deco))


def log_var_dict(var_dict):
    logger.info('Variable dictionary:\n'.format(datetime.datetime.now()))

    for key, val in var_dict.items():
        logger.info('{} = {}'.format(key, val))

    logger.info('All variables in Variable dictionary listed.\n'.format(datetime.datetime.now()))


def log_deleting(confirmed):
    """
    Log when the user selected to delete the system

    :param confirmed: A boolean value that indicates if the user confirmed to delete the system
    :return:
    """
    logger.info('{}'.format('*'*20))
    logger.info('Deleting system, wait for user confirmation')
    if not confirmed:
        logger.info('Failed to get confirmation from user. Abort deleting system')
    else:
        logger.info('User confirmed to delete system')
        logger.info('system deleted')
    logger.info('StarlingX Auto-installer finished.\n{}'.format('*'*20))


def log_debug_msg(msg):
    logger.debug('{}'.format(msg))


def log_info_msg(msg):
    logger.info('{}'.format(msg))


def log_error_msg(msg):
    logger.error('{}'.format(msg))