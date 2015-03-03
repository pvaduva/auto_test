
# WHICH FREE_TOTAL    FREE_2M  USED_2M     FREE_1G     USED_1G    

; test with valid hugepage values on $CPTNAME

$used1g=$USED_1G
?if $USED_1G == None ? [
    $used1g=0
]

$used2m == $USED_2M
?if $USED_2M == None ? [
    $used_2m=0
]

; calculate 1G PAGE NUMBER 
>echo $(( ( $FREE_TOTAL - 1) / 1024  ))
+$n_1g=\n([0-9]+)

?if $n_1g < 0 ? [
    $n_1g=0
]

; calculate 2M PAGE NUMBER 
>echo $(( ($FREE_TOTAL - $n_1g * 1024) / 2 ))
+$n_2m=\n([0-9]+)

?if $n_2m < 0 ? [
    $n_2m=0
]

;;;
; calculate 1G PAGE NUMBER 
>echo $(( ( $FREE_TOTAL - $used1g * 1024 - $used2m * 2 - 1) / 1024  ))
+$n_1g=\n([0-9]+)

?if $n_1g < 0 ? [
    $n_1g=0
]


; calculate 2M PAGE NUMBER 
>echo $(( $FREE_2M - ( $used1g + $n_1g ) * 512 - $used2m ))
+$n_2m=\n([0-9]+)

?if $n_2m < 0 ? [
    $n_2m=0
]

; 2m-hugepage: $n_2m 1g-hugepage: $n_1g
;;;
