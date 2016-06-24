
from pytest import fixture, mark
from time import sleep

from utils import table_parser, cli, exceptions
from utils.tis_log import LOG

from consts.auth import Tenant
from consts.cgcs import VMStatus, FlavorSpec, NetworkingVmMapping
from keywords import vm_helper, nova_helper, host_helper, glance_helper,system_helper


def test_sample():
    dic1 = {"headers":[1,2,3],'values':[[1,2,3],[4,5,6]]}
    dic2 = {"headers":[1,2],'values':[[1,2,3],[6,7]]}

    a = table_parser.compare_tables(dic1, dic2)

    assert a !=0, "comparsion should fail"

    dic1 = {"headers":[1,2,3],'values':[[1,2,3],[4,5,6]]}
    dic2 = {"headers":[1,2,3],'values':[[4,5,6],[1,2,3]]}

    a = table_parser.compare_tables(dic1, dic2)

    assert a !=0, "comparsion should fail"