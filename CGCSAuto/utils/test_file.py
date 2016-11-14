def parseResFile(resfile):
    passnum = passrate = failnum = failrate = totalnum = skipnum = -1
    testcase_list = []
    with open(resfile, mode='r') as f:
        for line in f:

            if 'Passed\t' in line or 'Failed\t' in line:
                testcase_list.append(line + '<br>')
            elif 'Passed:' in line:
                passres = line.split(sep=' ')
                passnum = int(passres[1].strip())
                passrate = float(passres[2].replace('(', '').replace(')', '').strip())
            elif 'Failed:' in line:
                failres = line.split(sep=' ')
                failnum = int(failres[1].strip())
                failrate = float(failres[2].replace('(', '').replace(')', '').strip())
            elif 'Total:' in line:
                totalnum = int(line.split(' ')[1].strip())
            elif 'Skipped:' in line:
                skipnum = int(line.split(' ')[1].strip())

    testcase_list = ''.join(testcase_list)
    return passnum, passrate, failnum, failrate, totalnum, skipnum, testcase_list