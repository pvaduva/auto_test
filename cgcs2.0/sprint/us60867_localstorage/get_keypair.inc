
;;;
Get the keypair of the current tenant

Required inputs:

Optional inputs:

;;;


;get the first keypair of tenant:$tenant_user
>nova keypair-list
+$keypair=\|\s* ([^\s]+) \s*\|\s* [a-z0-9:]+ \s*\|
? $keypair == __NO_STRING_CAPTURED__ ? [
    ;red EROOR: failed to get keypair for tenant:$tenant_user
    *FAIL
]

;keypair=$keypair

