;;;
Get the uuid of an availabe volume

Required inputs:
    <vlmnm>     name of the volume to create if none available

Optional inputs:
    <size>      size of the volume, default 1G
;;;

$vlmnm=vlm01
$size=1

;get one of the available volumes
>cinder list | awk '{if ($4 == "available" && $8 == 1) print $2}' | head -n1
+$vlmid=([0-9a-f-]{32,36})

? $vlmid == __NO_STRING_CAPTURED__ ? [
    ;no volume available
    ;create one
    
    ;first get cgcs-guest image
    ~get_img.inc
    
    ;create volume
    >cinder create --display-name $vlmnm --image-id $cgcs_img_id $size
    +$vlmid=\|\s* id \s*\|\s* ([0-9a-f-]{32,36}) \s*\|

    ? $vlmid == __NO_STRING_CAPTURED__ ? [
        ;error: failed to create volume
        *FAIL
    ]

    ;wait the volume to be ready
    ~wait_vlm_ready.inc vlmid=$vlmid
]

