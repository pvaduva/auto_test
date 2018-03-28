#!/usr/bin/python3

import argparse


def handle_args():
    """
    Handle arguments supplied to the command line
    """

    parser = argparse.ArgumentParser(formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--controllers", help=
        """
        Number of controllers:
          1 - single controller
          2 - two controllers
        """,
        choices=[1, 2],
        type=int)

    parser.add_argument("--computes", help=
        """
        Number of computes:
          1 - single compute
          2 - two computes
          etc.
        """,
        type=int)

    parser.add_argument("--storage", help=
        """
        Number of storage nodes:
          1 - single storage node
          2 - two storage nodes
          etc.\n
        """,
        type=int)

    parser.add_argument("--aio", help=
        """
        If present, install controllers as controller+compute nodes.
        """,
        action='store_true')
        
    parser.add_argument("--createlab", help=
        """
        If specified we will create and install new vms for the lab, otherwise the creation and install will be skipped. 
        Should be omitted when the vms have already been created and installed.
        """,
        action='store_true')
        
    parser.add_argument("--deletelab", help=
        """
        If present, delete existing lab. 
        """,
        action='store_true')

    parser.add_argument("--useexistinglab", help=
        """
        If present, don't create new VMs, use the existing ones.
        """,
        action='store_true')
    # WEI TODO: remove
    #parser.add_argument("--enablehttps", help=
    #    """
    #    If present, use https system config file else use http config file
    #    """,
    #    action='store_true')

    parser.add_argument("--release", help=
        """
        Which release to install:
          R2 - 15.12
          R3 - 16.10 
          R4 - 17.06
          R5 - 17.07
        """,
        choices=['R2', 'R3', 'R4', 'R5'],
        type=str,
        required=False)


    parser.add_argument("--buildserver", help=
        """
        Which build server to use:
          CGTS1 - yow-cgts1-lx
          CGTS2 - yow-cgts2-lx
          CGTS3 - yow-cgts3-lx
          CGTS4 - yow-cgts4-lx
        """,
        choices=['CGTS1', 'CGTS2', 'CGTS3', 'CGTS4'],
        type=str)

    parser.add_argument("--securityprofile", help=
        """
        Security profile to use:
          standard
          extended
        Standard is the default
        """,
        type=str, choices=['standard', 'extended'],
        default='standard')

    parser.add_argument("--lowlatency", help=
        """
        Whether to install an AIO system as low latency.
        """,
        action='store_true')

    parser.add_argument("--iso-location", help=
        """
        Location of ISO including the filename:
            /folk/cgts/myousaf/bootimage.ISO
        """,
        type=str)

    parser.add_argument("--useexistingiso", help=
        """
        If specified, we won't grab a new ISO but instead will use the existing
        one.  Typically stored at /tmp/bootimage.iso.
        """,
        action='store_true')

    parser.add_argument("--install-lab", help=
        """
        If specified, the nodes and lab will be installed automatically.
        """,
        action='store_true')

    parser.add_argument("--setup-files", help=
        """
        If specified the config files (i.e. lab_setup.sh, lab_setup.conf, license.lic, ...) will be retrieved from this location.
        e.g.  /folk/cgts/myousaf/
        """,
        type=str)
        
    parser.add_argument("--config-file", help=
        """
        If specified the config file (i.e. TiS_config.ini_centos, ...) will be retrieved from this local location.
        e.g.  /folk/cgts/myousaf/TiS_config.ini_centos
        """,
        type=str)
    parser.add_argument("--get-config", help=
        """
        If specified the config file (i.e. TiS_config.ini_centos, ...) will be retrieved from the buildserver specified.
        """,
        action="store_true")
    parser.add_argument("--configure", help=
        """
        If specified we will configure controller-0 otherwise the configuration will have to be perfomed manually. 
        config_controller will be run with the --default parameter.
        """,
        action='store_true')
        
    parser.add_argument("--install-patches", help=
        """
        If specified patches will be installed.
        """,
        action="store_true")
        
    parser.add_argument("--patch-dir", help=
        """
        Location of patch to install including patch name, if specified the patchs will be retrieved from the directory given.
        e.g. /folk/tmather/patches/
        """,
        type=str)

    parser.add_argument("--get-setup", help=
        """
        If specified, files will be retrieved from the buildserver.

        """,
        action='store_true')
    parser.add_argument("--get-patches", help=
        """
        If specified, patches will be retrieved from the buildserver.

        """,
        action='store_true')
        
    parser.add_argument("--install-mode", help=
        """
        Lab will be installed using the mode specified. Serial mode by default
        """,
        type=str, choices=['serial', 'graphical'], default='serial'
        )
    parser.add_argument("--run-scripts", help=
        """
        If specified the lab_setup.sh iterations will be run.
        """,
        action='store_true')
    parser.add_argument("--nessus", help=
        """
        Runs installer with the appropreate arguments for nessus scan setup. Currently requires files to be in the default folders.
        """,
        action='store_true')
    parser.add_argument("--complete", help=
        """
        Runs installer with the appropreate arguments for end to end setup. Retrieves files from a buildserver which mus be specified.
        """,
        action='store_true')
    parser.add_argument("--snapshot", help=
        """
        Take snapshot at different stages when the lab is installed. e.g. before and after config_controller, before and after lab_setup.
        """,
        action='store_true')
    parser.add_argument("--debug-rest", help=
        """
        Wei Uses this option to debug the rest of installation after controller-0 is unlocked 
        """,
        action='store_true')
    parser.add_argument("--username", help=
        """
        Username. default is 'wrsroot'
        """,
        type=str)
    parser.add_argument("--password", help=
        """
        Password. default is 'Li69nux*'
        """,
        type=str)
    parser.add_argument("--labname", help=
        """
        The name of the lab to be created.
        """,
        type=str)
    parser.add_argument("--controller0-ip", help=
        """
        OAM IP of controller-0 
        """,
        type=str)
    # WEI TODO: remove 
    #parser.add_argument("--lvm", help=
    #    """
    #    Configures storage with lvm backend.
    #    """,
    #    action='store_true')
    return parser
