#!/bin/bash
# INI file writer for MongoDB submitter
# little ini creation script - Craig Miller 8 May 2015
# ccw, 2015nov20 update to suport tags field


function usage {
               echo "	$0 - wassp manual submision INI creation script "
	       echo "	e.g. $0  [-n joeblow]" 
	       echo "	"
	       echo "	-d		Domain: system, sanity, regression, etc"
	       echo "	-o		output INI file"
	       echo "	-n		tester Name"
	       echo "	-t		Test"
	       echo "	-r		Result: PASS/FAIL"
	       echo "	-j		Jira"
	       echo "	-l		Lab used"
	       echo "	-b		Build that was used during test"
	       echo "	-u		User Story number"
	       echo "	-a		Artifcact or log file"
	       echo "	-T		List of test tags"
	       echo "	"
	       echo " By Craig Miller - Version: 0.96"
	       echo " Updated by Maria Yousaf - Version: 0.97"
	       echo " Updated by Maria Yousaf - Version: $VERSION"
	       exit 1
           }



VERSION=0.98

#outfile=$1
#testername=$2
#testname=$3
#result=$4
#lab=$5
#build=$6
#logfile=$7

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
release_name=""
#tag=""

# test
#./ini_writer.sh -D -o a -n b -t c -r pass -a junk -d init -j " " -l LLL -u US 

#note have to put in all options, otherwise getopts will choke
while getopts "hDo:x:n:t:a:r:l:b:d:j:u:R:" options; do
  case $options in
    o ) outfile="$OPTARG"
        let numopts+=2;;
    x ) tags="$OPTARG"
        let numopts+=2;;
    n ) testername="$OPTARG"
        let numopts+=2;;
    t ) testname="$OPTARG"
        let numopts+=2;;
    r ) result="$OPTARG"
        let numopts+=2;;
    l ) lab="$OPTARG"
        let numopts+=2;;
    a ) logfile="$OPTARG"
        let numopts+=2;;
    b ) build="$OPTARG"
        let numopts+=2;;
    d ) domain="$OPTARG"
        let numopts+=2;;
    j ) jira="$OPTARG"
        let numopts+=2;;
    u ) userstory="$OPTARG"
        let numopts+=2;;
    R ) release_name="$OPTARG"
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

echo "outfile: ${outfile}"
echo "DEBUG: ${DEBUG}"

echo "[default]" >> $outfile
echo "testerName = $testername" >> $outfile
echo "testName = $testname" >> $outfile
echo "status = $result" >> $outfile
echo "statusDetail = $result" >> $outfile
echo "testToolName = Manual" >> $outfile
echo "tags = ${tags}" >> $outfile
echo "tcTotal = 1" >> $outfile
echo "tcPassed = 1" >> $outfile
echo "userStories = $userstory" >> $outfile
echo "releaseName = ${release_name}" >> $outfile

echo "defects=$jira" >> $outfile
# env id
echo "environmentId = titanium_server_15" >> $outfile
echo "environmentName = FullInstall" >> $outfile
echo "environmentSpin = " >> $outfile




echo "[attributes]" >> $outfile
echo "project = CGCS 2.0" >> $outfile
echo "board_name = TiS" >> $outfile
echo "kernel = 3.10.71-ovp-rt74-r1_preempt-rt" >> $outfile
echo "domain=$domain" >> $outfile
echo "lab = $lab" >> $outfile
echo "build = $build" >> $outfile

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
cat $outfile > /tmp/cw_outfile.txt


if [ "$logfile" != "" ]; then
	echo "console = $logfile " >> $outfile
fi

if [ $DEBUG -eq 0 ]; then 
	cat $outfile
fi


#echo "==="
#ls -l /tmp/uploads/$logfile
#echo "</pre>"
#echo "---"
#echo "pau"


