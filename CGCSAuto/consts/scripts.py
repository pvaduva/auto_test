class GuestServiceScript:
    script_path = "/etc/init.d/tis_automation_setup_kernel_routing.sh"
    service_name = "tis_automation_setup_kernel_routing.service"
    service_path = "/etc/systemd/system/{}".format(service_name)
    service = """
[Unit]
Description=TiS Automation Kernel Routing Initialization
After=NetworkManager.service network.service wrs-guest-setup.service

[Service]
Type=simple
RemainAfterExit=yes
ExecStart=/bin/bash {} start
ExecStop=/bin/bash {} stop

[Install]
WantedBy=multi-user.target
""".format(script_path, script_path)

    _script = r"""
#!/bin/bash
################################################################################
# Copyright (c) 2014-2015 Wind River Systems, Inc.
#
# The right to copy, distribute, modify, or otherwise make use of this
# software may be licensed only pursuant to the terms of an applicable Wind
# River license agreement.
#
################################################################################
# chkconfig: 2345 10 99

function setup_netif_multiqueue()
{
    local IFNAME=$1

    DRIVER=$(basename $(readlink /sys/class/net/${IFNAME}/device/driver))
    if [ "$DRIVER" == "virtio_net" ]; then
        CPU_COUNT=$(cat /proc/cpuinfo |grep "^processor"|wc -l)

        CPU_START=0
        CPU_END=$((CPU_COUNT-1))

        if [ "$LOW_LATENCY" == "yes" ]; then
            # CPU 0 should not be used when configured for low latency
            # since VCPU0 does not run as a realtime thread
            CPU_START=1
            CPU_COUNT=$((CPU_COUNT-1))
        fi

        ethtool -L ${IFNAME} combined $CPU_COUNT

        QUEUE=0
        for ((CPUID=$CPU_START; CPUID <= $CPU_END; CPUID++))
        do
            CPUMASK=$(echo "(2^${CPUID})" | bc -l)
            IFNUMBER=${IFNAME#eth}
            IRQ=$(cat /proc/interrupts | grep "virtio${IFNUMBER}-input.${QUEUE}" | awk '{print $1}' | sed 's/://')
            echo ${CPUMASK} > /proc/irq/${IRQ}/smp_affinity
            QUEUE=$((QUEUE+1))
        done
    fi

    return 0
}

function setup_kernel_routing()
{
    echo 1 > /proc/sys/net/ipv4/ip_forward
    echo 0 > /proc/sys/net/ipv4/conf/default/rp_filter
    echo 0 > /proc/sys/net/ipv4/conf/all/rp_filter
    echo 1 > /proc/sys/net/ipv6/conf/default/forwarding
    echo 1 > /proc/sys/net/ipv6/conf/all/forwarding
    modprobe 8021q
    for IFNAME in $(find /sys/class/net -maxdepth 1 -type l -exec basename {} \\;); do
        if [[ $IFNAME != "lo" ]]; then
            echo "${IFNAME}" | grep -q "\\."
            if [ $? -eq 0 ]; then
                # VLAN is being created, create interface and setup underlying interface
                UIFNAME=$(echo ${IFNAME}|awk -F '.' '{print $1}')
                VLANID=$(echo ${IFNAME}|awk -F '.' '{print $2}')

                # enable multiqueue support if using the virtio-net driver
                setup_netif_multiqueue ${UIFNAME}
            else
                setup_netif_multiqueue ${IFNAME}
            fi
            echo 0 > /proc/sys/net/ipv4/conf/${IFNAME}/rp_filter
            echo 1 > /proc/sys/net/ipv6/conf/${IFNAME}/forwarding
        fi
    done
    return 0
}

################################################################################
# Start Action
################################################################################
function start()
{
    setup_kernel_routing
    return 0
}

################################################################################
# Stop Action
################################################################################
function stop()
{
    return 0
}

################################################################################
# Status Action
################################################################################
function status()
{
    return 0
}

################################################################################
# Main Entry
################################################################################

case "$1" in
  start)
        start
        ;;
  stop)
        stop
        ;;
  restart)
        stop
        start
        ;;
  status)
        status
        ;;
  *)
        echo $"Usage: $0 {start|stop|restart|status}"
        exit 1
esac

exit 0

"""
    @classmethod
    def generate_script(cls, **kwargs):
        return "\n".join(["{}={}".format(*kv) for kv in kwargs.items()]+[cls._script])
