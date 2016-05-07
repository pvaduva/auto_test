
# Copyright (c) 2016 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.
#

from setuptools import setup, find_packages

setup(
    name='labinstall',
    description='Automated lab install',
    version='1.0.0',
    license='windriver',
    packages = ['.', 'node_info', 'lab_settings','utils'],
    package_data = {'node_info': ['*.ini'],
                    'lab_settings': ['*.ini']},
    entry_points={
        'console_scripts': [
            'install_system = install_system:main',
        ]}

)
