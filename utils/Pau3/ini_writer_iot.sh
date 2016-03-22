#!/bin/bash
# INI file writer for MongoDB submitter
# little ini creation script - Craig Miller 8 May 2015

# Updated for IoT group	22 May 2015

# Updated for IoT group, adding Release & Env Names	22 May 2015

function usage {
               echo "	$0 - wassp manual submision INI creation script "
	       echo "	e.g. $0  [-n TC999]" 
	       echo "	"
	       echo "	-d		Domain: system, sanity, regression, etc"
	       echo "	-o		output INI file"
	       echo "	-n		tester Name"
	       echo "	-t		Test"
	       echo "	-r		Result: PASS/FAIL"
	       echo "	-j		Jira"
	       echo "	-P		Project Name"
	       echo "	-b		Barcode of device"
	       echo "	-u		User Story number"
	       echo "	-a		Artifcact or log file"
	       echo "	-N		Board Name"
	       echo "	-B		BSP"
	       echo "	-C		Config Label"
	       echo "	-R		Release Name"
	       echo "	-E		Envionment Name"
	       echo "	-T		Tag"
	       echo "	"
	       echo " By Craig Miller - Version: $VERSION"
	       exit 1
           }



VERSION=0.97


domain="TEST"
logfile="none"

#script defaults
NUMBER_REMOVE=0
DEBUG=0

testname="none"
testername="none"
jira=""
result="ZZZ"
lab=""
build=""
logfile=""
userstory=""
board_name=""
bsp=""
config_label=""
release_name=""
tag=""
bar_ocde=""
project=""


#	Called by:
# $pipe = popen ("$cdir/$pau_ini_writer -o $outfile -n \"$tester_name\"  -t \"$test_name\"  -r \"$passfail\" -l \"$lab\"  -b \"$build\" -a \"$logfile\" -j \"$jira\"  -u \"$userstory\" -d $domain   -N \"$board_name\"  -B \"$bsp\"  -C \"$config_label\"  -R \"$release_name\"    -T \"$tag\" ", "r");

# test
#./ini_writer_iot.sh -D -o a -n b -t c -r pass -a junk -d init -j " " -u US -N aaa -B bbb -C ccc -R rrr -T ttt -b 123 -P IoT -E EnvName


#note have to put in all options, otherwise getopts will choke
while getopts "hDo:n:t:a:r:b:d:j:u:N:B:C:R:E:T:P:" options; do
  case $options in
    o ) outfile="$OPTARG"
        let numopts+=2;;
    n ) testername="$OPTARG"
        let numopts+=2;;
    t ) testname="$OPTARG"
        let numopts+=2;;
    r ) result="$OPTARG"
        let numopts+=2;;
    a ) logfile="$OPTARG"
        let numopts+=2;;
    b ) barcode="$OPTARG"
        let numopts+=2;;
    d ) domain="$OPTARG"
        let numopts+=2;;
    j ) jira="$OPTARG"
        let numopts+=2;;
    u ) userstory="$OPTARG"
        let numopts+=2;;
    N ) board_name="$OPTARG"
        let numopts+=2;;
    B ) bsp="$OPTARG"
        let numopts+=2;;
    C ) config_label="$OPTARG"
        let numopts+=2;;
    R ) release_name="$OPTARG"
        let numopts+=2;;
    E ) env_name="$OPTARG"
        let numopts+=2;;
    T ) tag="$OPTARG"
        let numopts+=2;;
    P ) project="$OPTARG"
        let numopts+=2;;


    D ) DEBUG=1
    	let numopts+=1;;
    h ) usage;;
    \? ) usage	# show usage with flag and no value
         exit 1;;
	# allow unknown flags
    #* ) usage		# show usage with unknown flag
    #	 exit 1;;
  esac
  if [ $DEBUG -gt 0 ]; then 
  	echo "$options $OPTARG"
  fi
done
# remove the options as cli arguments
shift $numopts

# check that there are no arguments left to process
#if [ $# -ne 0 ]; then
#	usage
#	exit 1
#fi

if [ "$testname" == "none" ]; then
	usage
	exit 1
fi

if [ "$testername" == "none" ]; then
	usage
	exit 1
fi

if [ $DEBUG -gt 0 ]; then 
	# change output file to stdout for debugging
	outfile="/dev/stdout"
fi


#======== Actual work performed by script ============




echo "[default]" >> $outfile
echo "testerName = $testername" >> $outfile
echo "testName = $testname" >> $outfile
echo "status = $result" >> $outfile
echo "statusDetail = $result" >> $outfile
echo "testToolName = Manual" >> $outfile
echo "tcTotal = 1" >> $outfile
echo "tcPassed = 1" >> $outfile
echo "userStories = $userstory" >> $outfile

echo "defects=$jira" >> $outfile
# env id
echo "environmentId = $env_name" >> $outfile
echo "environmentName = $env_name" >> $outfile
echo "environmentSpin = " >> $outfile
# IoT values
echo "releaseName = $release_name" >> $outfile
echo "tags = $tag" >> $outfile


echo "[attributes]" >> $outfile
# IoT values

echo "project = $project" >> $outfile
echo "bsp = $bsp" >> $outfile
echo "boardName = $board_name" >> $outfile
echo "config_label = $config_label" >> $outfile
echo "bar_code = $barcode ">> $outfile

#echo "kernel = 3.10.71-ovp-rt74-r1_preempt-rt" >> $outfile
echo "domain=$domain" >> $outfile
# pass target via -l $lab
echo "target = $lab" >> $outfile
#echo "build = $build" >> $outfile

echo "[build]" >> $outfile
echo "status = PASS" >> $outfile
echo "statusDetail = PASS" >> $outfile

echo "[boot]" >> $outfile
echo "status = PASS" >> $outfile
echo "statusDetail = PASS" >> $outfile

echo "[runtimeconfig]" >> $outfile
echo "status = PASS" >> $outfile
echo "statusDetail = PASS" >> $outfile

echo "[exec]" >> $outfile
echo "status = $result" >> $outfile
echo "statusDetail = $result" >> $outfile
if [ "$logfile" != "" ]; then
	echo "console = $logfile " >> $outfile
fi

#echo "<pre>$outfile"

if [ $DEBUG -eq 0 ]; then 
	cat $outfile
fi


#echo "==="
#ls -l /tmp/uploads/$logfile
#echo "</pre>"
#echo "---"
#echo "pau"


