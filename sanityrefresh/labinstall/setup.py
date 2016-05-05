#
# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.
#

import setuptools

setuptools.setup(
    name='install_system',
    description='Automated lab install',
    version='1.0.0',
    license='windriver',
    packages=['labinstall', 'labinstall.utils'],
    package_data={'labinstall': ['node_info/*.ini', 'lab_settings/*.ini']},

)
