from keywords import system_helper
from utils import table_parser


def test_func():
    print(system_helper.get_servicegroup_list(['service_group_name', 'uuid'], hostname='controller-1', state='disabled'))

