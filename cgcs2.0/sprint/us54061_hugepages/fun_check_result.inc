
;;;
    Wait the status of the specified cinder volume changed to STATUS (specified)
    input:
    HOSTNAME
    PERSONALITY
    #ADMINISTRATIVE
    #OPERATIONAL
    #AVAILABILITY
;;;

#~fun_wait_till_states.inc HOSTNAME=$HOSTNAME PERSONALITY=$PERSONALITY ADMINISTRATIVE=locked OPERATIONAL=disabled AVAILABILITY=online


