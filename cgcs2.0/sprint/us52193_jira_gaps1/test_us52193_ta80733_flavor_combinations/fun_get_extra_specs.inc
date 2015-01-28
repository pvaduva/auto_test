
; get extra specs of flavor $FLVID
; param1: FLVID=<$FLVID>

# for test only
#  {"dedicated:cpus": "True", "guest:heartbeat": "False"}
#| extra_specs                | {"dedicated:cpus": "True", "guest:heartbeat": "False"} |
#$FLVID=41546f8a-84d0-40a3-8887-99b6d918b6e0

>nova flavor-show $FLVID
+$DDTD_CPUS=\|\s*extra_specs\s*\|\s*{"dedicated:cpus":\s*"([a-zA-Z]+)",
+$GST_HREARTBEAT="guest:heartbeat":\s*"([a-zA-Z]+)"




