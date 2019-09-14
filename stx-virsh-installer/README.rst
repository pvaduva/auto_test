STX-Virsh-Installer
=================
This project can be used to install StarlingX system on Qemu-KVM.
Supported StarlingX system mode:

- Simplex
- Duplex
- Standard
- Storage

Detailed information about StarlingX system can be found from Installation and Deployment Guides:
https://docs.starlingx.io/deploy_install_guides/index.html

Packages Required
-------
- python >='3.2, <=3.7.2'
- pexpect
- paramiko

Installing
------
- Install above packages

- Run /stx-virsh-installer/libvirt_scripts/install_packages.sh


Example Usage
--------
Set /path/to/stx-virsh-installer as working directory.
To install StarlingX system with template file and default setup, execute::

    SYSTEM_MODE="simplex"
    python3 -m stx-virsh-installer -m $SYSTEM_MODE


To delete the installed StarlingX system, execute::

    SYSTEM_MODE="simplex"
    python3 -m stx-virsh-installer -m $SYSTEM_MODE -d


SYSTEM_MODE should be one of: simplex, duplex, standard or storage.

To check all start arguments, execute::

    python3 -m stx-virsh-installer -h


To install StarlingX system with custom settings:
	- Modify the installer_config.ini file.
	- Use -o /path/to/overwrite_file after the default installation command
	- Use -c /path/to/custom_files_directory after the default installation command to install
	StarlingX system with custom files that will not be dynamically modified by stx-virsh-installer
	- Use -t /path/to/custom_template_files_directory after
	the default installation command to install StarlingX system with
	custom template files that will be dynamically modified by stx-virsh-installer

Please check /stx-virsh-installer/installer_config.ini for detailed information about
overwriting custom variables and providing custom files


Default workflow
---------
- Create the directory for storing logs and download files if not exists

- Download necessary files

- Set up network and create virtual machines using scripts in libvirt_scripts based on config file
  and system mode

- Boot controller-0

- Transfer files needed for deployment manager to controller-0

- Populate template files

- Run lab-install-playbook.yaml

- Wait for controller-0 to be unlocked

- Boot other nodes if needed and wait for all nodes to be ready

- Run lab_setup.sh