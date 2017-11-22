#!/usr/bin/python3

def pytest_addoption(parser):
    parser.addoption("--controllers", help=
        """
        Number of controllers:
          1 - single controller
          2 - two controllers
        """,
        choices=[1, 2],
        type=int, required=True)

    parser.addoption("--computes", help=
        """
        Number of computes:
          1 - single compute
          2 - two computes
          etc.
        """,
        type=int)

    parser.addoption("--storage", help=
        """
        Number of storage nodes:
          1 - single storage node
          2 - two storage nodes
          etc.\n
        """,
        type=int)

    parser.addoption("--aio", help=
        """
        If present, install controllers as controller+compute nodes.
        """,
        action='store_true')

    parser.addoption("--deletevms", help=
        """
        If present, delete existing VMs. 
        """,
        action='store_true')

    parser.addoption("--useexistingvms", help=
        """
        If present, don't create new VMs, use the existing ones.
        """,
        action='store_true')

    parser.addoption("--release", help=
        """
        Which release to install:
          R2 - 15.12
          R3 - 16.10 
          R4 - 17.06
          R5 - 17.07
        """,
        choices=['R2', 'R3', 'R4', 'R5'],
        type=str)

    parser.addoption("--buildserver", help=
        """
        Which build server to use:
          CGTS1 - yow-cgts1-lx
          CGTS2 - yow-cgts2-lx
          CGTS3 - yow-cgts3-lx
          CGTS4 - yow-cgts4-lx
        """,
        choices=['CGTS1', 'CGTS2', 'CGTS3', 'CGTS4'],
        type=str)

    parser.addoption("--iso-host", help=
        """
        Which host to get the ISO from:
           localhost 
           yow-cgts4-lx
           yow-cgts3-lx
           etc.
        """,
        type=str)

    parser.addoption("--securityprofile", help=
        """
        Security profile to use:
          standard
          extended
        Standard is the default
        """,
        type=str, choices=['standard', 'extended'],
        default='standard')

    parser.addoption("--lowlatency", help=
        """
        Whether to install an AIO system as low latency.
        """,
        action='store_true')

    parser.addoption("--iso-location", help=
        """
        Location of ISO including the filename:
            /folk/cgts/myousaf/bootimage.ISO
        """,
        type=str)

    parser.addoption("--useexistingiso", help=
        """
        If specified, we won't grab a new ISO but instead will use the existing
        one.  Typically stored at /tmp/bootimage.iso.
        """,
        action='store_true')

def pytest_generate_tests(metafunc):
    option_value = metafunc.config.option.name
    if 'name' in metafunc.fixturenames and option_value:
        metafunc.parameterize("name", [option_value])
