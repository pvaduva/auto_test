# Set up the virtual display

#TYPE export DISPLAY=127.0.0.1:8 \n
TYPE xhost + \n
CALL ./start_vncserver.sh
