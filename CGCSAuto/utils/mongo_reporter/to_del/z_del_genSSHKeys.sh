#!/bin/bash
#
# genSSHKeys.sh - SSH Authentication Keys generator
#
# Copyright (c) 2012, 2014 Wind River Systems Inc.
#
# The right to copy, distribute, modify or otherwise make use
# of this software may be licensed only pursuant to the terms
# of an applicable Wind River license agreement.
#
# Script can be used to set up automatic SSH authentication
#
# Usage:
#   - User can call this script without parameters (interactive mode)
#   - Script can be called with: ip port username password customConfig
#
# CustomConfig is a 1/0 flag specifying if a temporary SSH
# configuration file should be used (the personal keys of the user are not used)
#
# modification history:
#---------------------
# 10jan14,srr  Set ForwardAgent for SSH and don't wait for the deletion of password file
# 01c,07nov12,srr   Added a more shell-independent method for remote SSH keys setup
# 01b,14oct12,srr   Added interactive parameter setup
# 01a,11oct12,srr   Created
#

# SSH server information
SSH_DEST_IP=$1
SSH_DEST_PORT=$2
SSH_DEST_USERNAME=$3
SSH_DEST_PASSWORD=$4
SSH_DEST_CUSTOMCONFIG=$5

# Get information from user if not enough parameters have been specified
if [ $# -lt 1 ]; then 
    read -p "Please enter the SSH host IP: " SSH_DEST_IP
fi

if [ $# -lt 2 ]; then
    read -p "Please enter the SSH host port: " SSH_DEST_PORT
fi

if [ $# -lt 3 ]; then
    read -p "Please enter SSH username: " SSH_DEST_USERNAME
fi

if [ $# -lt 4 ]; then
    read -s -p "Please enter SSH password: " SSH_DEST_PASSWORD
    echo -e "\n"
fi

# define the remote user SSH authorized keys file name
AUTH_KEY_FILE=authorized_keys

# define an empty SSH options list
CUSTOMPARAM=

# define default user key file
SSH_KEY_FILE=~/.ssh/id_dsa


check_ssh_login()
{
    # check if SSH user can login without password (keys have been setup)

    # ssh to host and redirect output to bitbucket
    # automatically accept NEW hosts
    ssh $CUSTOMPARAM -o PreferredAuthentications=publickey -o UserKnownHostsFile=/dev/null -o StrictHostKeyChecking=no -p $SSH_DEST_PORT $SSH_DEST_USERNAME@$SSH_DEST_IP exit > /dev/null 2>&1

    SSH_STATUS=$?
    # check ssh command exit code
    if [ $SSH_STATUS -eq 0 ]; then
        echo "SSH keys OK"
        # exit if keys are setup
        exit 0
    elif [ $SSH_STATUS -eq 255 ]; then
        return 1
    else
        echo "Can not connect to $SSH_DEST_IP"
        exit 1
    fi
}

setup_ssh_keys()
{
    echo "Trying to set up SSH keys for $SSH_DEST_IP"
    

    # define a temporary custom configuration file if requested
    # This has a few advantages:
    # - user may have password protected keys which would have to be unlocked by ssh-agent (password prompt)
    # - user does not want to use his own keys
    # - the host at an IP may change over time (Revo assigns random machines to random IPs) 
    #   resulting in SSH believing there is a man-in-the-middle attack until the hosts file is fixed (TODO?)
    #   a new hosts file and automatic acceptance of new hosts bypasses this problem here
    if [ "$SSH_DEST_CUSTOMCONFIG" = "1" ]; then
        # create a custom config file
        CONFIG_FILE="$(mktemp)"
        # create a known_hosts file
        HOSTS_FILE="$(mktemp)"
        chmod 700 $CONFIG_FILE $HOSTS_FILE
        # create a custom keys file name and delete the file, it will be created later
        SSH_KEY_FILE="$(mktemp)"
        rm $SSH_KEY_FILE
        echo $CONFIG_FILE $SSH_DEST_CUSTOMCONFIG
        # set up the configuration file
        echo "Host *
        UserKnownHostsFile $HOSTS_FILE
        IdentityFile $SSH_KEY_FILE
        StrictHostKeyChecking no
        ForwardAgent yes
        " > $CONFIG_FILE
        
        # output the configuration file name for the user
        echo %@%$CONFIG_FILE%@%
        
        # set the custom parameters option to use the custom config file
        CUSTOMPARAM="-F $CONFIG_FILE"
    fi

    # create public/private keys if they don't exit
    if [ ! -f $SSH_KEY_FILE -a ! -f $SSH_KEY_FILE.pub ]; then
        if ! ssh-keygen -t dsa -f $SSH_KEY_FILE -N ""; then
            echo "Failed to create public/private keys"
            exit 1
        fi
    fi

    # create a temporary password file
    PASSWORD_SCRIPT="$(mktemp)"
    
    # schedule deletion of temporary password file
    (sleep 60 && rm $PASSWORD_SCRIPT) > /dev/null 2>&1 &

    # write temporary password output script
    echo "#!/bin/bash
    echo $SSH_DEST_PASSWORD" > $PASSWORD_SCRIPT
    
    # make script executable
    chmod 700 $PASSWORD_SCRIPT

    # set the SSH client password script
    # this will be used by the SSH client for the password if not attached to a tty
    export SSH_ASKPASS=$PASSWORD_SCRIPT

    # set the display if not set
    if [ ! "$DISPLAY" ]; then
        export DISPLAY=:0.0
    fi

    # use hostname as a file name
    HOSTNAME=`hostname`
    
    # transfer the public key to the SSH server
    setsid scp $CUSTOMPARAM -P $SSH_DEST_PORT $SSH_KEY_FILE.pub $SSH_DEST_USERNAME@$SSH_DEST_IP:~/"$HOSTNAME"_id.pub < /dev/null

    # create the SSH key file on the server
    setsid ssh $CUSTOMPARAM -p $SSH_DEST_PORT $SSH_DEST_USERNAME@$SSH_DEST_IP mkdir -p '~/.ssh' \; chmod 700 '~/.ssh; touch ~/.ssh/'$AUTH_KEY_FILE

    CMD_FILE="$(mktemp)"
    
    # setup a bash script that will add the public key to the authorized keys file
    echo '#!/bin/bash
    if grep "cat '$HOSTNAME'_id.pub" .ssh/'$AUTH_KEY_FILE' > /dev/null;
    then
        true
    else
        cat '$HOSTNAME'_id.pub >> .ssh/'$AUTH_KEY_FILE'
    fi
    rm '$HOSTNAME'_id.pub' > $CMD_FILE
    
    # make the script executable
    chmod 700 $CMD_FILE
    
    # transfer the script to the destination host
    setsid scp $CUSTOMPARAM -P $SSH_DEST_PORT $CMD_FILE $SSH_DEST_USERNAME@$SSH_DEST_IP:~/"$HOSTNAME"_id < /dev/null
    
    # add the public key to the remote user SSH authorized keys file
    setsid ssh $CUSTOMPARAM -p $SSH_DEST_PORT $SSH_DEST_USERNAME@$SSH_DEST_IP '~/'"$HOSTNAME"_id
    
    # delete the script file from the remote host
    setsid ssh $CUSTOMPARAM -p $SSH_DEST_PORT $SSH_DEST_USERNAME@$SSH_DEST_IP 'rm ~/'"$HOSTNAME"_id
    
    # delete the script file
    rm $CMD_FILE 2>/dev/null
    
    # delete the temporary password file
    rm $PASSWORD_SCRIPT 2>/dev/null
}

if ! check_ssh_login; then
    # try to create SSH keys if they are not setup
    setup_ssh_keys

    if ! check_ssh_login; then
        echo "Failed to setup SSH keys for $SSH_DEST_IP"
        exit 255
    fi
fi
