
;;;
Get the UUID of cgcs-guest

Required inputs:

Optional inputs:
    <image_name>    'cgcs-guest' by default

;;;

;get the image id
>glance image-list | awk '{if ($4 == "cgcs-guest" && $12 == "active") print $2}'
+$cgcs_img_id=\s*([0-9a-f-]{32,36})\s*
? $cgcs_img_id == __NO_STRING_CAPTURED__ ? [
    ;ERROR: no cgcs-image found 
    *FAIL
]

;uuid of cgcs-guest image is: $cgcs_img_id

