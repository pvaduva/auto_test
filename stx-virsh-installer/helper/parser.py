import argparse


def add_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument('-m', '-M', '--mode',
                        help='Specify system mode (simplex, duplex, standard or controllerstorage,'
                             ' storage or dedicatedstorage)',
                        required=True)
    parser.add_argument('-o', '-O', '--overwrite',
                        help='Specify the path to the file that contains all'
                             ' the overwrite parameters,'
                             ' check readme for detailed information')
    parser.add_argument('-c', '-C', '--customize',
                        help='Specify the path to the directory that contains all customized files,'
                             ' check readme for detailed information')
    parser.add_argument('-t', '-T', '--template',
                        help='Specify the path to the directory that contains '
                             'all customized template files,'
                             ' check readme for detailed information')
    parser.add_argument('-d', '-D', '--delete', help='Delete the installed system',
                        action='store_true')
    parser.add_argument('--skipvm', help='Skip creating new virtual machines',
                        action='store_true')
    return parser
