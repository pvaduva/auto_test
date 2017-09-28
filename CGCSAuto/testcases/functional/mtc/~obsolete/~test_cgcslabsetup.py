import os
import subprocess
from time import sleep

from consts.proj_vars import ProjVar
from consts.auth import HostLinuxCreds
from consts.filepaths import WRSROOT_HOME
from keywords import host_helper
from utils.ssh import ControllerClient
from utils.tis_log import LOG

WRSUSER=HostLinuxCreds.get_user()
WRSPASS=HostLinuxCreds.get_password()
WRSDIR=WRSROOT_HOME
USER=os.environ['USER']
WASSP_TESTCASE_BASE='/home/{}/wassp-repos/testcases/cgcs'.format(USER)
BUILDSERVER='128.224.145.134'
JKPATH='/localdisk/loadbuild/jenkins/'
LOADPATH='CGCS_3.0_Centos_Build/'
GUESTPATH='CGCS_3.0_Guest_Daily_Build/'
PUBLIC_NETWORK='tenant1-net1'
PUBLIC_ROUTER='tenant1-router'
CONTROLLER_PROMPT = '.*controller\-[01].*\$ '


def test_cgcslabsetup(con_ssh=None):
    """
    Execute shell commands in order to prepare the lab for executing sanity test cases.

    """

    LOG.tc_step("Execute shell scripts")
    if not con_ssh:
        con_ssh = ControllerClient.get_active_controller()
    if not con_ssh.get_hostname() == 'controller-0':
        host_helper.swact_host()

    con_ssh.set_prompt(CONTROLLER_PROMPT)
    cmd = '''echo 'export HISTTIMEFORMAT="%Y-%m-%d %T "' >> ~/.bashrc'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''echo "export TMOUT=0" >> ~/.bashrc'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    #cmd = '''echo 'export PROMPT_COMMAND="date; $$PROMPT_COMMAND"'  >> ~/.bashrc'''
    #code, output = con_ssh.exec_cmd(cmd)
    #sleep(10)
    cmd = '''source ~/.bashrc'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''echo {} | sudo -S sed -i.bkp "s/TMOUT=900/TMOUT=/g" /etc/profile'''.format(WRSPASS)
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''echo {} | sudo -S chmod -R 755 /var/log'''.format(WRSPASS)
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''source /etc/nova/openrc'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)

    LOG.tc_step("Update the quotas")

    cmd = '''adminid=`keystone tenant-list |grep admin|awk '{print $2}'`'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''tenant1=`keystone tenant-list |grep tenant1|awk '{print $2}'`'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''tenant2=`keystone tenant-list |grep tenant2|awk '{print $2}'`'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)

    cmd = '''neutron quota-update --tenant-id $$adminid --network 500 --subnet 500 --port 333 --router 100 --floatingip 222'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''cinder quota-update --snapshots 100 --volumes 100 $$adminid'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''nova quota-update --instances 200 --cores 200 --floating-ips 254 --fixed-ips 254   $$adminid'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)

    cmd = '''neutron quota-update --tenant-id $$tenant1 --network 500 --subnet 500 --port 333 --router 100 --floatingip 222'''
    code, output = con_ssh.exec_cmd(cmd)
    cmd = '''cinder quota-update --snapshots 100 --volumes 100 $$tenant1'''
    sleep(10)
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''nova quota-update --instances 200 --cores 200 --floating-ips 254 --fixed-ips 254   $$tenant1'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)

    cmd = '''neutron quota-update --tenant-id $$tenant2 --network 500 --subnet 500 --port 333 --router 100 --floatingip 222'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''cinder quota-update --snapshots 100 --volumes 100 $$tenant2'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)
    cmd = '''nova quota-update --instances 200 --cores 200 --floating-ips 254 --fixed-ips 254   $$tenant2'''
    code, output = con_ssh.exec_cmd(cmd)
    sleep(10)

    LOG.tc_step("import SSH public and private keys")

    lab = ProjVar.get_var("LAB")
    print('LAB_ARG: {}'.format(lab))
    #lab = setups.get_lab_dict(lab_arg)
    oamAddrA = lab['floating ip']
    oamAddrB = lab['controller-1 ip']
    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ~/.ssh/id_rsa {}@{}:{}/.ssh/".format(WRSPASS, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)

    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ~/.ssh/id_rsa.pub {}@{}:{}/.ssh/".format(WRSPASS, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)

    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ~/.ssh/authorized_keys {}@{}:{}/.ssh/".format(WRSPASS, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)

    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ~/.ssh/id_rsa {}@{}:{}/.ssh/".format(WRSPASS, WRSUSER, oamAddrB, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)

    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ~/.ssh/id_rsa.pub {}@{}:{}/.ssh/".format(WRSPASS, WRSUSER, oamAddrB, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)

    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ~/.ssh/authorized_keys {}@{}:{}/.ssh/".format(WRSPASS, WRSUSER, oamAddrB, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)

    LOG.tc_step("Copy guest images, heat templates and other scripts")

    code, output = con_ssh.exec_cmd("mkdir {}/images {}/heat {}/bin".format(WRSDIR, WRSDIR, WRSDIR))
    sleep(10)

    LOG.tc_step("copy some utilities")
    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}/utils/setupCgcsNetworking.sh {}@{}:{}/bin/".format(WRSPASS, WASSP_TESTCASE_BASE, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)
    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}/utils/setupCgcsNetworkVars.sh {}@{}:{}/bin/".format(WRSPASS, WASSP_TESTCASE_BASE, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)
    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}/utils/system_host_list_wait.sh {}@{}:{}/bin/".format(WRSPASS, WASSP_TESTCASE_BASE, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)
    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}/utils/system_host_stor_add.sh {}@{}:{}/bin/".format(WRSPASS, WASSP_TESTCASE_BASE, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)
    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}/utils/ceph_health_wait.sh {}@{}:{}/bin/".format(WRSPASS, WASSP_TESTCASE_BASE, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)
    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}/utils/create_tempestconf.sh {}@{}:{}/bin/".format(WRSPASS, WASSP_TESTCASE_BASE, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)
    #CALL python3 ${WASSP_TESTCASE_BASE}/utils/sendFile.py -i $env.NODE.target.Boot.oamAddrA -u ${WRSUSER} -p ${WRSPASS} -s /folk/${EXECUTOR}/bin/sshpass -d /usr/bin/ -P 22
    cmd = "sshpass -p {} rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' /folk/{}/bin/sshpass {}@{}:{}/bin/".format(WRSPASS, USER, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)
    con_ssh.exec_cmd('chmod -R 777 {}/bin/'.format(WRSDIR))
    con_ssh.exec_cmd("nova keypair-add --pub_key ~/.ssh/id_rsa.pub controller-0")
    con_ssh.exec_cmd("nova keypair-list")
    con_ssh.exec_cmd("neutron net-list")
    con_ssh.exec_cmd("mkdir -p {}/images/".format(WRSDIR))
    con_ssh.exec_cmd('mkdir -p {}/heat/'.format(WRSDIR))

    #CALL ${WASSP_TC_PATH}/../utils/findLatestCgcsLoad2.sh ${BUILDSERVER} > ${WASSP_TC_RUN_LOG}/cgcs_load.log
    #CALL cat ${WASSP_TC_RUN_LOG}/cgcs_load.log

    #SET CR }
    #SET CL {
    #CALLPARSER echo $CL\"LOAD_PATH\":\"`cat ${WASSP_TC_RUN_LOG}/cgcs_load.log`\"$CR

    #############################################
    # Temporary workaroud:
    # SET LOAD /localdisk/loadbuild/jenkins/CGTS_1.0_Unified_Daily_Build/2014-01-04_01-32-25/
    #############################################
    # TODO:  the ssh/rsync user should be  leaned at runtime
    # Download the latest Cirros guest VM images to controller-0
    # TYPE rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ${EXECUTOR}@$BUILDSERVER:/${LOAD_PATH}/layers/wr-cgcs/cgcs/extras.ND/scripts/ ~/images/ \n

    cmd = "rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@{}:{}{}/latest_build/layers/wr-cgcs/cgcs/extras.ND/scripts/ {}/images/ ".format(USER, BUILDSERVER, JKPATH, LOADPATH, WRSDIR)
    con_ssh.exec_cmd(cmd)
    sleep(30)

    # get the ubuntu cloud image.  This image is only available in Scott Little private dir
    # hard coding the cgts2 build server IP because the image only exists in scotts directory
    cmd = "rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@128.224.150.21:/home/svc-cgcsauto/precise-server-cloudimg-amd64-disk1.img {}/images/precise-server-cloudimg-amd64-disk1.img".format(USER, WRSDIR)
    con_ssh.exec_cmd(cmd)
    sleep(30)

    # Grab 3rd party guest images from: yow-cgts2-lx:/localdisk/designer/jenkins/images/precise-server-cloudimg-amd64-disk1.img
    # TYPE rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' ${EXECUTOR}@$BUILDSERVER:/localdisk/designer/jenkins/images/ ~/images/ \n
    # WAIT 1000 SEC

    # Copy lab setup config for specific lab - as defined by labsetup variable contained in the target ini file
    #cmd = "rsync -av -e 'ssh -o ConnectTimeout=20 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@{}:{}{}/latest_build/layers/wr-cgcs/cgcs/extras.ND/lab/yow/$env.NODE.target.Boot.labsetup/* {}/".format(USER, BUILDSERVER, JKPATH, LOADPATH, WRSDIR)
    #con_ssh.exec_cmd(cmd)
    #sleep(20)

    cmd = "rsync -av -e 'ssh -o ConnectTimeout=20 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@{}:{}{}/latest_build/layers/wr-cgcs/cgcs/extras.ND/lab/scripts/* {}/".format(USER, BUILDSERVER, JKPATH, LOADPATH, WRSDIR)
    con_ssh.exec_cmd(cmd)
    sleep(20)

    cmd = "rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@{}:{}{}/cgcs-guest.img {}/images/".format(USER, BUILDSERVER, JKPATH, GUESTPATH, WRSDIR)
    con_ssh.exec_cmd(cmd)
    sleep(30)

    # copy the default heat templates
    cmd = "rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@{}:{}{}/latest_build/bitbake_build/tmp/deploy/cgcs_sdk/* {}/".format(USER, BUILDSERVER, JKPATH, LOADPATH, WRSDIR)
    con_ssh.exec_cmd(cmd)
    sleep(30)

    cmd = "rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@{}:{}{}/latest_build/layers/wr-cgcs/cgcs/extras.ND/heat_templates/* {}/heat/".format(USER, BUILDSERVER, JKPATH, LOADPATH, WRSDIR)
    con_ssh.exec_cmd(cmd)
    sleep(30)

    # Heat template path is hardcoded to Unified Daily Build directory temporarily
    cmd = "rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@{}:{}/CGCS_3.0_Unified_Daily_Build/latest_build/export/heat_templates/* {}/heat/".format(USER, BUILDSERVER, JKPATH, WRSDIR)
    con_ssh.exec_cmd(cmd)
    sleep(30)

    cmd = "rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@{}:{}/CGCS_3.0_Centos_Build/latest_build/repo/addons/wr-cgcs/layers/cgcs/openstack/recipes-base/python-heat/python-heat/templates/* {}/heat/".format(USER, BUILDSERVER, JKPATH, WRSDIR)
    con_ssh.exec_cmd(cmd)
    sleep(30)

    # Temporary workaroudn to pull in testid.py into nosetest
    cmd = "rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}@{}:/folk/cgts/users/{}/testid.py /usr/lib64/python2.7/site-packages/nose/plugins/".format(USER, BUILDSERVER, USER)
    con_ssh.exec_cmd(cmd)
    sleep(30)

    con_ssh.exec_cmd("tar -xvf *heat*.tgz")
    con_ssh.exec_cmd('cp -pR wrs-heat*/* heat')

    # root should have alread loged in via loginCGCS.frag
    con_ssh.exec_cmd('chmod -R 777 {}/images/'.format(WRSDIR))
    con_ssh.exec_cmd('chmod -R 777 {}/heat/'.format(WRSDIR))
    con_ssh.exec_cmd('cat /etc/build.info')

    # synch-up  controller-1 to controller-0
    con_ssh.exec_cmd("rsync -avr -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' {}/images controller-1:{}/".format(WRSDIR, WRSDIR))
    sleep(30)
    con_ssh.exec_cmd("rsync -avr -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' {}/bin controller-1:{}/".format(WRSDIR, WRSDIR))
    sleep(30)
    con_ssh.exec_cmd("rsync -avr -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' {}/heat controller-1:{}/".format(WRSDIR, WRSDIR))
    sleep(30)
    con_ssh.exec_cmd("rsync -avr -e 'ssh -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no ' {}/ controller-1:{}/".format(WRSDIR, WRSDIR))
    sleep(30)

    #####################################################################################
    # Create VM image and Start it
    #####################################################################################
    LOG.tc_step("Create glance images for VMs and start them")

    con_ssh.exec_cmd("glance image-create --name cirros --is-public true --container-format bare --disk-format qcow2 --file ~/images/cirros-0.3.0-x86_64-disk.img --property hw_vif_model=e1000")
    sleep(30)
    con_ssh.exec_cmd("glance image-list")
    sleep(30)
    con_ssh.exec_cmd("glance image-create --name wrl5-avp --is-public true --container-format bare --disk-format qcow2 --file ~/images/cgcs-guest.img --property hw_vif_model=avp")
    sleep(30)
    con_ssh.exec_cmd("glance image-create --name wrl5-virtio --is-public true --container-format bare --disk-format qcow2 --file ~/images/cgcs-guest.img --property hw_vif_model=virtio")
    sleep(35)
    # New as of June 12 2014:
    con_ssh.exec_cmd("glance image-create --name wrl5 --is-public true --container-format bare --disk-format qcow2 --file ~/images/cgcs-guest.img")
    sleep(35)
    # New as of July 22 2014:
    con_ssh.exec_cmd("glance image-create --name ubuntu-precise-amd64 --is-public true --container-format bare --disk-format qcow2 --file ~/images/precise-server-cloudimg-amd64-disk1.img")
    sleep(300)

    # for backwrard compatibility:
    # TYPE glance image-create --name cgcs-guest --is-public true --container-format bare --disk-format raw --file ~/images/cgcs-guest.img \n
    # WAIT 30 SEC

    con_ssh.exec_cmd("nova flavor-create wrl5.dpdk.big 100 4096 0 3")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-create wrl5.dpdk.small 101 512 0 2")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-create --dedicated-cpus True m1.small 2 2048 20 1")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-create --dedicated-cpus True --guest-heartbeat True  wrl5.dpdk.small.heartbeat 200 512 0 2")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-create --dedicated-cpus True --guest-heartbeat True  wrl5.dpdk.big.heartbeat 201 4096 0 3")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-create --dedicated-cpus True --guest-heartbeat True  --shared-vcpu 0  wrl5.dpdk.big.heartbeat.pinToMgmtCore  233 4096 0 3")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-create --dedicated-cpus True m1.tiny 1 512 1 1")
    sleep(30)

    ####  New way to create flavors in R2
    ####  commands above will fail silently in R2 but will be backwards compatible with R1
    LOG.tc_step("Create flavors")

    con_ssh.exec_cmd("nova flavor-create m1.small 2 2048 20 1")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-key m1.small set hw:cpu_policy=dedicated hw:mem_page_size=2048")
    sleep(30)

    con_ssh.exec_cmd("nova flavor-create  wrl5.dpdk.small.heartbeat 200 512 0 2")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-key wrl5.dpdk.small.heartbeat set hw:cpu_policy=dedicated hw:mem_page_size=2048")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-create  wrl5.dpdk.big.heartbeat 201 4096 0 3")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-key wrl5.dpdk.big.heartbeat set hw:cpu_policy=dedicated hw:mem_page_size=2048")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-create  wrl5.dpdk.big.heartbeat.pinToMgmtCore  233 4096 0 3")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-key wrl5.dpdk.big.heartbeat.pinToMgmtCore set hw:cpu_policy=dedicated hw:mem_page_size=2048")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-create  m1.tiny 1 512 1 1")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-key m1.tiny set hw:cpu_policy=dedicated hw:mem_page_size=2048")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-key wrl5.dpdk.small set hw:cpu_policy=dedicated hw:mem_page_size=2048")
    sleep(30)
    con_ssh.exec_cmd("nova flavor-key wrl5.dpdk.big set hw:cpu_policy=dedicated hw:mem_page_size=2048")
    sleep(30)

    #### Create tempest.conf file
    # TODO: this file needs to be lab specifica based on info in the controller-0 target.in for a particularlab
    # It should contain designated VLANids as per: http://twiki.wrs.com/PBUeng/CGTelcoServerLabConn

    cmd = "rsync -av -e 'ssh -o ConnectTimeout=2000 -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no' {}/utils/create_tempestconf.sh {}@{}:{}/bin/".format(WASSP_TESTCASE_BASE, WRSUSER, oamAddrA, WRSDIR)
    build = subprocess.check_output(cmd, shell=True).decode('ascii')
    sleep(30)

    #con_ssh.exec_cmd("~/bin/create_tempestconf.sh $env.NODE.target.Boot.NATIP $env.NODE.target.Boot.NATUSER $env.NODE.target.Boot.NATPASS $env.NODE.target.Boot.computeA $env.NODE.target.Boot.computeB $env.NODE.target.Boot.controllerA $env.NODE.target.Boot.controllerB {} {} admin {}".format(NAT_IP, NATUSER, NATPASS, PUBLIC_NETWORK, PUBLIC_ROUTER, WRSPASS))
    #sleep(60)
    #con_ssh.exec_cmd("cat ~/bin/create_tempestconf.sh")
    #sleep(60)

    con_ssh.exec_cmd("echo set tabstop=4 > ~/.vimrc")
    con_ssh.exec_cmd("echo set ignorecase >> ~/.vimrc")
    con_ssh.exec_cmd("echo syntax on >> ~/.vimrc")
    con_ssh.exec_cmd("echo set hlsearch >> ~/.vimrc")
    con_ssh.exec_cmd("echo set shiftwidth=4 >> ~/.vimrc")
    con_ssh.exec_cmd(" cho set expandtab >> ~/.vimrc")
    con_ssh.exec_cmd("echo set mouse-=a >> ~/.vimrc")
    sleep(10)


    #con_ssh.exec_cmd("system modify name=$env.NODE.target.Boot.labsetup")
    con_ssh.exec_cmd('system modify description="This system belongs to CGCS project"')
    sleep(10)

    con_ssh.exec_cmd("nova list")
    sleep(10)
    #SAVEOUTPUT /tmp/nova-list.log
    # SAVEOUTPUT ${WASSP_TC_USER_WORKSPACE}/myFile

    ## CALLPARSER echo $CL\"LOAD_PATH\":\"`cat ${WASSP_TC_PATH}/cgcs_load.log`\"$CR
    ## {"LOAD_PATH":"/localdisk/loadbuild/jenkins/CGTS_1.0_Unified_Daily_Build/2014-01-04_01-32-25/"}
    ## CALL cat /tmp/nova-list.log|grep cirros-1 | awk 'BEGIN {FS = "=||\;" } {print $2}' > /tmp/cirrosip.txt

    #CALL cat /tmp/nova-list.log|grep cirros-1 | awk 'BEGIN ${CL} FS = "=||;"${CR} ${CL} print $$2${CR}' > /tmp/cirrosip.txt
    #CALLPARSER echo ${CL}\"CIRROS0IP\":\"`cat /tmp/cirrosip.txt`\"${CR}

    # CALL ssh cgcs@128.224.150.11 ping -c1 192.168.101.2


    con_ssh.exec_cmd("chown -R wrsroot.wrs /home/wrsroot/ ")

