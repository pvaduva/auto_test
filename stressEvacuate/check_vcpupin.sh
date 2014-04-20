#!/bin/bash


if `virsh dumpxml $1 | grep  -q vcpupin`
then
echo vcpupin exists
else echo vcpupin missing
fi
