#!/usr/bin/env bash
#
# SPDX-License-Identifier: Apache-2.0
#
# Copyright (C) 2019 Intel Corporation
#

SCRIPT_DIR="$(dirname "$(readlink -f "${BASH_SOURCE[0]}" )" )"
source ${SCRIPT_DIR}/functions.sh
WORKERNUM=2
STORAGENUM=2
PREFIX=""
while getopts "c:i:w:s:p:" o; do
    case "${o}" in
        c)
            CONFIGURATION="$OPTARG"
            ;;
        i)
            ISOIMAGE=$(readlink -f "$OPTARG")
            ;;
	w)
	    WORKERNUM=$OPTARG;;
	s)
	    STORAGENUM=$OPTARG;;
	p)
	    PREFIX=${OPTARG};;
        *)
            usage
            exit 1
            ;;
    esac
done
shift $((OPTIND-1))

if [[ -z ${CONFIGURATION} ]] || [[ -z "${ISOIMAGE}" ]]; then
    usage
    exit -1
fi

iso_image_check ${ISOIMAGE}
configuration_check ${CONFIGURATION}

CONFIGURATION=${CONFIGURATION:-simplex}
BRIDGE_INTERFACE=${BRIDGE_INTERFACE:-stxbr}
CONTROLLER=${CONTROLLER:-controller}
WORKER=${WORKER:-worker}

#WORKER_NODES_NUMBER=${WORKER_NODES_NUMBER:-1}
WORKER_NODES_NUMBER=${WORKERNUM}

STORAGE=${STORAGE:-storage}

#STORAGE_NODES_NUMBER=${STORAGE_NODES_NUMBER:-1}
STORAGE_NODES_NUMBER=${STORAGENUM}

DOMAIN_DIRECTORY=vms

if [ -z "$PREFIX" ]
then
      bash ${SCRIPT_DIR}/destroy_configuration.sh -c $CONFIGURATION -w $WORKERNUM -s $STORAGENUM
else
      bash ${SCRIPT_DIR}/destroy_configuration.sh -c $CONFIGURATION -p $PREFIX -w $WORKERNUM -s $STORAGENUM
fi


[ ! -d ${DOMAIN_DIRECTORY} ] && mkdir ${DOMAIN_DIRECTORY}
echo prefix is ${PREFIX}
create_controller $CONFIGURATION $CONTROLLER $BRIDGE_INTERFACE $ISOIMAGE ${PREFIX}

if ([ "$CONFIGURATION" == "controllerstorage" ] || [ "$CONFIGURATION" == "dedicatedstorage" ]); then
    for ((i=0; i<$WORKER_NODES_NUMBER; i++)); do
        WORKER_NODE=${PREFIX}${CONFIGURATION}-${WORKER}-${i}
        create_node "worker" ${WORKER_NODE} ${BRIDGE_INTERFACE} 
    done
fi

if ([ "$CONFIGURATION" == "dedicatedstorage" ]); then
    for ((i=0; i<$STORAGE_NODES_NUMBER; i++)); do
        STORAGE_NODE=${PREFIX}${CONFIGURATION}-${STORAGE}-${i}
        create_node "storage" ${STORAGE_NODE} ${BRIDGE_INTERFACE} 
    done
fi

sudo virt-manager
