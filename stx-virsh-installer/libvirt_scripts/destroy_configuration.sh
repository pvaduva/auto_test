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
while getopts "c:w:s:p:" o; do
    case "${o}" in
        c)
            CONFIGURATION=${OPTARG}
            ;;
	w)
	    WORKERNUM=$OPTARG;;
	s)
	    STORAGENUM=$OPTARG;;
	p)
	    PREFIX=${OPTARG};;
        *)
            usage_destroy
            exit 1
            ;;
    esac
done
shift $((OPTIND-1))

if [[ -z ${CONFIGURATION} ]]; then
    usage_destroy
    exit -1
fi

configuration_check ${CONFIGURATION}

CONFIGURATION=${CONFIGURATION:-simplex}
CONTROLLER=${CONTROLLER:-controller}
DOMAIN_DIRECTORY=vms

destroy_controller ${CONFIGURATION} ${CONTROLLER} ${PREFIX}

if ([ "$CONFIGURATION" == "controllerstorage" ] || [ "$CONFIGURATION" == "dedicatedstorage" ]); then
    WORKER=${WORKER:-worker}
    WORKER_NODES_NUMBER=${WORKERNUM}
#    WORKER_NODES_NUMBER=${WORKER_NODES_NUMBER:-1}
    for ((i=0; i<$WORKER_NODES_NUMBER; i++)); do
        WORKER_NODE=${PREFIX}${CONFIGURATION}-${WORKER}-${i}
        destroy_node "worker" $WORKER_NODE
    done
fi

if ([ "$CONFIGURATION" == "dedicatedstorage" ]); then
    STORAGE=${STORAGE:-storage}
    STORAGE_NODES_NUMBER=${STORAGENUM}
#    STORAGE_NODES_NUMBER=${STORAGE_NODES_NUMBER:-1}
    for ((i=0; i<$STORAGE_NODES_NUMBER; i++)); do
        STORAGE_NODE=${PREFIX}${CONFIGURATION}-${STORAGE}-${i}
        destroy_node "storage" ${STORAGE_NODE}
    done
fi
