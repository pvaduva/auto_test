<?php echo '<?xml version="1.0"?' . '>'; ?>
<!DOCTYPE html PUBLIC "-//WAPFORUM//DTD XHTML Mobile 1.0//EN" "http://www.wapforum.org/DTD/xhtml-mobile10.dtd">

<html>
 <head>
<?php
// Expect-lite web runner v0.9
// by Craig Miller 8 May 2015
// 

// 22 May 2015 v0.96 - added themes, so other groups can use the web front end

// 2 June 2015 v0.97 - Updated IoT fields Release/Env Name

// 2 June 2015 v0.98 - Updated to not push empty log file (removing odd error)


// script version
$version=0.99;

// ===== Change these vars to valid values in your environment ====
// path to this script and ini_writer scripts
$path="/folk/svc-cgcsauto/public_html/Pau3/";
// default ini path
//$ini_path="/tmp/uploads";
$ini_path="/home/svc-cgcsauto/uploads";

$ini_name="results.ini";
//$dir_name="/tmp/uploads";
$dir_name="/home/svc-cgcsauto/uploads/";
// wassp directory
//$wassp_dir="/localdisk/WASSP/";
$wassp_dir="/home/svc-cgcsauto/wassp-repos/";

//ini file writer script
$pau_ini_writer="ini_writer.sh";

// script defaults
$jira="";
$domain="TEST";
$theme="";
// board used in test
$target="";
//release,env name
$rel_env="";
//$tag="system";

// ================================================================

// set Theme (allow other users than TiS
 if (!empty($_GET)) {
	 if (isset($_GET["theme"])) {
 		$theme=$_GET["theme"];
		}
 }

 if (!empty($_POST)) {
	 if ($_POST["theme"] != '') {
 		$theme=$_POST["theme"];
		}
 }

// set info based on theme - supported TiS, IoT
 if ($theme=="") {
 	$theme="tis";
 }
 
 if ($theme=="iot") {
 	$theme_title="IoT";
	$bg="aero_bike_gear_cluster_shadowed_cls_bg.jpg";
	$pau_ini_writer="ini_writer_iot.sh";
	// board used in test
	$target="";

 } else  {
 	// default theme if bad theme is entered by user
	$theme="tis";
 	$theme_title="TiS";
	$bg="paia_bambo_blinds_bg.jpg";
	$pau_ini_writer="ini_writer.sh";
 }




?>

  <style type="text/css">
body {
text:"#000000" ;
bgcolor:"#ffffff" ;
background-image: url("<?php echo $bg ?>");
link:"#0000ee" ;
vlink:"#551a8b";
alink:"#ff0000" ;
padding:30px;
}
.opaque_box {
background-image: url("opacity.png");
background-image: url('opacity.png');border: thin groove blue; padding: 1em; -moz-border-radius: 10px;
-webkit-border-radius: 10px; max-width:900px; margin:auto;
}
</style>
 
 
<?php


// ================================================================



function pau_submit($theme,$ofile,$tester_name,$test_name,$passfail,$lab,$build,$logfile,$jira,$userstory,$domain,$cdir,$board_name,$bar_code,$bsp,$config_label,$release_name,$tag,$project,$env_name) {

	// defaults
	//$domain="system";

	// write ini file
	//$pau_ini_writer="ini_writer.sh";
	$pau_ini_writer=$GLOBALS['pau_ini_writer'];
	$outfile=$GLOBALS['ini_path'] . "/" . $ofile;
	
	// if log file is not empty, give full path 
	if ($logfile != "") {
		$logfile= $GLOBALS['dir_name'] . "/" . $logfile;
	} 
	
	echo "<pre>debug_outfile: $outfile ";
	echo "<pre>debug_tag: $tag </br>";
	echo "<pre>debug_theme: $theme </br>";
	if ($theme == "tis") {
		$pipe = popen ("$cdir/$pau_ini_writer -o $outfile -x \"${tag},titanium_server_regression_r4,cgcs_manual\" -n \"$tester_name\"  -t \"$test_name\"  -r \"$passfail\" -l \"$lab\"  -b \"$build\" -a \"$logfile\" -j \"$jira\"  -u \"$userstory\" -d $domain -R \"$release_name\"", "r");
	}
	if ($theme == "iot") {
		$pipe = popen ("$cdir/$pau_ini_writer  -o $outfile -n \"$tester_name\"  -t \"$test_name\"  -r \"$passfail\"  -b \"$bar_code\" -a \"$logfile\" -j \"$jira\"  -u \"$userstory\" -d $domain   -N \"$board_name\"  -B \"$bsp\"  -C \"$config_label\"  -R \"$release_name\"    -E \"$env_name\"  -T \"$tag\"   -P \"$project\"", "r");
	}

	while(!feof($pipe)) {
		$line = fread($pipe, 1024);
		echo $line;
		// show partial output
		flush();	
	}
	pclose($pipe);
	echo "</pre>";
}



function write_mongodb($ofile) {

	$wdir=$GLOBALS['wassp_dir'];	
	$ini_file=$GLOBALS['ini_path'] . "/" . $ofile ;	
	echo "<pre>";
	$pipe = popen ("bash -c \"cd $wdir; source .venv_wassp/bin/activate; wassp/host/report/testReportManual.py -f $ini_file 2>&1 \" ", "r");
	while(!feof($pipe)) {
		$line = fread($pipe, 1024);
		echo $line;
		// show partial output
		flush();	
	}
	pclose($pipe);
	echo "</pre>";
}

function randomize_fname($name) {
	$length = 10;
    $fname = substr(str_shuffle("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"), 0, $length) . $name;
	return $fname;
}

?>
  <title>Pau</title>
 </head>
 <body>
<div class="opaque_box">




<?php

// ====== Show Form
 if (empty($_POST)) {
 	echo "<h1>$theme_title Manual Test - MongoDB Submit</h1>";
 	echo "<form action=\"pau.php\" method=\"POST\"  enctype=\"multipart/form-data\">";
	echo "  <input type=\"hidden\" name=\"comain\" value=\"$domain\" >";
	echo "  <input type=\"hidden\" name=\"theme\" value=\"$theme\" >";
?>



<table>
<tr>
<td>
	Tester Name:
	</td><td>
	<input name="tester" type="text"/></br>
	</td></tr><tr><td>

	Test Name: &nbsp; &nbsp;
	</td><td>	
	<input name="testname" type="text"/></br>
	</td></tr><tr><td>

	Test Result:&nbsp;&nbsp;&nbsp;
	</td><td>	
	<select name="passfail">
  		<option value="PASS">PASS</option>
  		<option value="FAIL">FAIL</option>
  		<option value="NA">NA</option>
	</select>
	
	</td></tr><tr><td>

	JIRA: &nbsp; &nbsp; 
	</td><td>	
	<input name="jira" type="text"/></br>
	</td></tr><tr><td>

	<?php
	if ($theme=="tis") {
	
		echo "Lab Used: &nbsp; &nbsp;";
		echo "</td><td>";	

		echo "<select name=\"lab\">";
  			echo "<option value=\"Ottawa_hp380\">Ottawa_hp380</option>";
  			echo "<option value=\"Ottawa_ironpass1-4\">Ottawa_ironpass1-4</option>";
  			echo "<option value=\"Ottawa_ironpass7-12\">Ottawa_ironpass7-12</option>";
  			echo "<option value=\"Ottawa_ironpass14-17\">Ottawa_ironpass7-12</option>";
  			echo "<option value=\"Ottawa_ironpass18-19\">Ottawa_ironpass7-12</option>";
  			echo "<option value=\"Ottawa_ironpass-20-27\">Ottawa_ironpass-20-27</option>";
  			echo "<option value=\"wcp7-12\">wcp7-12</option>";
 			echo "<option value=\"Ottawa_R720-1-2\">Ottawa_R720-1-2</option>";
 			echo "<option value=\"Ottawa_R720-3-7\">Ottawa_R720-3-7</option>";
 			echo "<option value=\"cgcs-pv-0\">cgcs-pv-0</option>";
 			echo "<option value=\"cgcs-pv-1\">cgcs-pv-1</option>";
 			echo "<option value=\"yow-cgcs-wildcat-7-12\">yow-cgcs-wildcat-7-12</option>";
 			echo "<option value=\"cgcs-wildcat-71_75\">cgcs-wildcat-71_75</option>";
  			echo "<option value=\"Other\">Other</option>";
			echo "<option value=\"Virtual_Box\" selected=\"selected\">Virtual_Box</option>";
		echo "</select>";
		// close table cell
		echo "</td></tr><tr><td>";


		echo "Test Domain:";
		echo "</td><td>";	

		echo "<select name=\"domain\">";
  			echo "<option value=\"Functional\">Functional</option>";
  			echo "<option value=\"System\">System</option>";
  			echo "<option value=\"Performance\">Performance</option>";
  			echo "<option value=\"Scale\">Scale</option>";
  			echo "<option value=\"Other\">Other</option>";
		echo "</select>";

		// close table cell
		echo "</td></tr><tr><td>";

		echo "Build Used:";
		echo "</td><td>";		
		echo "<input name=\"build\" type=\"text\"/></br>";


	}
	// if tis
	if ($theme=="iot") {

		echo "Project:";
		echo "</td><td>";	

		echo "<select name=\"project\" >";
  			echo "<option value=\"IoT EMS 1.1\">IoT EMS 1.1 </option>";
  			echo "<option value=\"IoT EMS 1.2\">IoT EMS 1.2</option>";
  			echo "<option value=\"IoT EMS 2.0\" selected>IoT EMS 2.0 aka Nova</option>";
		echo "</select>";

		// close table cell
		echo "</td></tr><tr><td>";

		echo "Release Name/<br>Environment Name:";
		echo "</td><td>";	
		// combination field: release & environment name
		echo "<select name=\"rel_env\" >";
  			echo "<option value=\"NOVA,IOT_EMS_2.0_-_Lx5\">NOVA, IOT_EMS_2.0_-_Lx5</option>";
  			echo "<option value=\"EMS 1.2,VxWorks7\">EMS 1.2, VxWorks7</option>";
  			echo "<option value=\"EMS 1.2,WRLinux7\">EMS 1.2, WRLinux7</option>";
  			echo "<option value=\"EMS 1.2,WRLinux7_IDP3\">EMS 1.2, WRLinux7_IDP3</option>";
		echo "</select>";

		// close table cell
		echo "</td></tr><tr><td>";
		echo "Board Name: &nbsp; &nbsp;";
		echo "</td><td>";	
	
		echo "<input name=\"board_name\" type=\"text\"/></br>";
		// close table cell
		echo "</td></tr><tr><td>";

		echo "Barcode: &nbsp; &nbsp;";
		echo "</td><td>";	
	
		echo "<input name=\"bar_code\" type=\"text\"/></br>";
		// close table cell
		echo "</td></tr><tr><td>";

		echo "BSP: &nbsp; &nbsp;";
		echo "</td><td>";	
	
		echo "<input name=\"bsp\" type=\"text\"/></br>";
		// close table cell
		echo "</td></tr><tr><td>";

		echo "Config Label: &nbsp; &nbsp;";
		echo "</td><td>";	
	
		echo "<input name=\"config_label\" type=\"text\"/></br>";
		// close table cell
		echo "</td></tr><tr><td>";

		echo "Tag: &nbsp; &nbsp;";
		echo "</td><td>";	
	
		echo "<input name=\"tag\" type=\"text\"/></br>";
		// close table cell
		echo "</td></tr><tr><td>";


		echo "Test Domain:";
		echo "</td><td>";	

		echo "<select name=\"domain\">";
  			echo "<option value=\"Unit\">Unit</option>";
  			echo "<option value=\"Functional\" selected>Functional</option>";
  			echo "<option value=\"Adversarial\">Adversarial</option>";
  			echo "<option value=\"Integration\">Integration</option>";
  			echo "<option value=\"System\">System</option>";
  			echo "<option value=\"Performance\">Performance</option>";
  			echo "<option value=\"Stress\">Stress</option>";
  			echo "<option value=\"OOBE\">OOBE</option>";
  			echo "<option value=\"Regression\">Regression</option>";
		echo "</select>";

		// close table cell
		echo "</td></tr><tr><td>";

		
	}
	// if iot
	?>


	</td></tr><tr><td>
	User Story: 
	</td><td>	
	<input name="userstory" type="text"/></br>
	</td></tr><tr><td>

        </td></tr><tr><td>
        Test Tags:
        </td><td>
        <input name="tag" type="text"/></br>
        </td></tr><tr><td>

        <?php
	echo "</td></tr><tr><td>";
        echo "Release Name:";
        echo "</td><td>";
        echo "<select name=\"release_name\">";
        echo "<option value=\"Titanium Server R3\">Titanium Server R3</option>";
        echo "<option value=\"Titanium Server 15.12\">Titanium Server 15.12</option>";
        echo "</select>";
        echo "</td></tr><tr><td>";
        ?>

</td></tr></table>

	<br/>
    Choose a Log file to be uploaded:
    <input name="myFile" type="file"/><br/>
<?php
	echo "  <input type=\"submit\" value=\"Submit-It\">";
	echo " </form> ";
	}
  else {
	// Get info from form and process it
	$tester_name=$_POST["tester"];
	$test_name=$_POST["testname"];
	$passfail=$_POST["passfail"];
	$jira=$_POST["jira"];
	// tis fields
	if ($_POST["build"] != '') {
		$build=$_POST["build"];
		$lab=$_POST["lab"];
	}
	$domain=$_POST["domain"];
	$userstory=$_POST["userstory"];
	$release_name=$_POST["release_name"];
	$tag=$_POST["tag"];
	//$logfile=$_POST["myFile"];
	$logfile=$_FILES['myFile']['name'];

	// iot fields
	if ($_POST["board_name"] != '') {
		$project=$_POST["project"];
		$board_name=$_POST["board_name"];
		$bar_code=$_POST["bar_code"];
		$bsp=$_POST["bsp"];
		$config_label=$_POST["config_label"];
		$tag=$_POST["tag"];
		$rel_env=$_POST["rel_env"];
		// split combo field
		$f_array = explode(",",$rel_env);
		$release_name = $f_array[0];
		$env_name = $f_array[1];
	}

	$outfile=randomize_fname($ini_name);

	if ($userstory == "DEBUG") {
		echo "<b>Uploaded File Info:</b><br/>";
		$l_type=$_FILES['myFile']['type'];
		$l_name=$_FILES['myFile']['name'];
		$l_size=$_FILES['myFile']['size'];
		$l_error=$_FILES['myFile']['error'];
		
		echo "Content type: $l_type <br/>";
		echo "Content type: $l_name <br/>";
		echo "Content type: $l_size<br/>";
		echo "Content type: $l_error <br/>";

	}


	// ====== upload the file
	if ($_FILES['myFile']['error'] == UPLOAD_ERR_OK){
  		$fileName = $_FILES['myFile']['name'];
	 
	  /* Save the uploaded file if its size is greater than 0. */
	  if ($_FILES['myFile']['size'] > 0){
    	  $fileName = basename($fileName);
    		if (move_uploaded_file($_FILES['myFile']['tmp_name'], $dir_name . "/" . $fileName)){
				echo "File has been uploaded<br>";
    		}
    		else{
				echo "<b>An error occurred when we tried to save the uploaded file.</b><br>";
			}
		}
	}
	
	// todo: validate values are present

	
	$cdir=getcwd();
	// run the script
	pau_submit($theme,$outfile,$tester_name,$test_name,$passfail,$lab,$build,$logfile,$jira,$userstory,$domain,$cdir,$board_name,$bar_code,$bsp,$config_label,$release_name,$tag,$project,$env_name);

	// write the MongoDB
	if ($userstory != "DEBUG") {
		write_mongodb($outfile);
	}
	echo "<p>---pau</p>";
	// remove temp ini file
	//unlink($ini_path . "/" . $outfile);
  }
?>





<HR />
<i>pau</i> version:<?php echo "$version"; ?>  &nbsp; &nbsp;  <small>by Craig Miller</small><BR>
</div>
 </body>
</html>
